"""FastAPI application for Tiro."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tiro.config import TiroConfig, load_config
from tiro.database import init_db, migrate_db
from tiro.decay import recalculate_decay
from tiro.vectorstore import init_vectorstore

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"


async def _imap_sync_loop(config: TiroConfig):
    """Background task that checks IMAP inbox on a schedule."""
    from tiro.ingestion.imap import check_imap_inbox

    while True:
        interval = config.imap_sync_interval
        if interval <= 0 or not config.imap_enabled:
            return

        await asyncio.sleep(interval * 60)

        if not config.imap_enabled or config.imap_sync_interval <= 0:
            return

        try:
            result = await asyncio.to_thread(check_imap_inbox, config)
            if result["fetched"] > 0:
                logger.info(
                    "IMAP sync: %d fetched, %d processed, %d skipped, %d failed",
                    result["fetched"], result["processed"],
                    result["skipped"], result["failed"],
                )
            else:
                logger.debug("IMAP sync: no new messages")
        except Exception as e:
            logger.error("IMAP sync failed: %s", e)


def _compute_sleep_until(time_str: str, tz_offset_minutes: int) -> float:
    """Compute seconds until next occurrence of HH:MM in user's timezone.

    Args:
        time_str: Target time as "HH:MM"
        tz_offset_minutes: JS-style getTimezoneOffset() (positive = west of UTC)
    """
    from datetime import timedelta

    hour, minute = int(time_str[:2]), int(time_str[3:5])
    now_utc = datetime.now(timezone.utc)

    # Convert user's local target time to UTC
    # JS getTimezoneOffset() returns minutes: UTC - local (e.g. EST = 300, CET = -60)
    user_offset = timedelta(minutes=-tz_offset_minutes)
    user_tz = timezone(user_offset)

    # Build today's target in user's timezone, then convert to UTC
    user_now = now_utc.astimezone(user_tz)
    target_local = user_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If target has already passed today, schedule for tomorrow
    if target_local <= user_now:
        target_local += timedelta(days=1)

    target_utc = target_local.astimezone(timezone.utc)
    delta = (target_utc - now_utc).total_seconds()
    return max(delta, 60)  # At least 60 seconds to avoid tight loops


async def _digest_schedule_loop(config: TiroConfig):
    """Background task that generates + emails digests on schedule."""
    from tiro.intelligence.digest import generate_digest
    from tiro.intelligence.email_digest import send_digest_email

    last_email_date = None

    while True:
        if not config.digest_schedule_enabled:
            return

        sleep_secs = _compute_sleep_until(config.digest_schedule_time, config.digest_timezone_offset)
        logger.info("Digest scheduler: next run in %.0f seconds (at %s)", sleep_secs, config.digest_schedule_time)
        await asyncio.sleep(sleep_secs)

        # Re-check config (may have been disabled while sleeping)
        if not config.digest_schedule_enabled:
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            result = await asyncio.to_thread(
                generate_digest, config, unread_only=config.digest_unread_only
            )
            logger.info("Scheduled digest generated for %s (%d sections)", today, len(result))

            # Auto-email if SMTP configured and haven't sent today
            if config.smtp_user and config.smtp_password and config.digest_email:
                if last_email_date != today:
                    try:
                        await asyncio.to_thread(send_digest_email, config, True)
                        last_email_date = today
                        logger.info("Scheduled digest emailed to %s", config.digest_email)
                    except Exception as e:
                        logger.error("Scheduled digest email failed: %s", e)
        except Exception as e:
            logger.error("Scheduled digest generation failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and vectorstore on startup."""
    config: TiroConfig = app.state.config

    # Ensure library directories exist
    config.articles_dir.mkdir(parents=True, exist_ok=True)
    (config.library / "audio").mkdir(parents=True, exist_ok=True)

    # Initialize SQLite + run migrations
    init_db(config.db_path)
    migrate_db(config.db_path)

    # Initialize ChromaDB with configured embedding model
    init_vectorstore(config.chroma_dir, config.default_embedding_model)

    # Recalculate content decay weights
    recalculate_decay(config)

    # Start IMAP sync background task if configured
    sync_task = None
    if config.imap_enabled and config.imap_sync_interval > 0:
        sync_task = asyncio.create_task(_imap_sync_loop(config))
        logger.info("IMAP sync started: every %d minutes", config.imap_sync_interval)

    # Start digest schedule background task if configured
    digest_task = None
    if config.digest_schedule_enabled:
        digest_task = asyncio.create_task(_digest_schedule_loop(config))
        logger.info("Digest schedule started: daily at %s", config.digest_schedule_time)
    app.state.digest_task = digest_task

    logger.info("Tiro is ready — library at %s", config.library)
    yield

    # Cancel background tasks on shutdown
    for task in [sync_task, digest_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_app(config: TiroConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if config is None:
        config = load_config()

    app = FastAPI(
        title="Tiro",
        description="A local-first reading OS for the AI age",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.config = config

    # CORS — allow local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    from tiro.api.routes_articles import router as articles_router
    from tiro.api.routes_digest import router as digest_router
    from tiro.api.routes_ingest import router as ingest_router
    from tiro.api.routes_search import router as search_router
    from tiro.api.routes_classify import router as classify_router
    from tiro.api.routes_decay import router as decay_router
    from tiro.api.routes_sources import router as sources_router
    from tiro.api.routes_stats import router as stats_router
    from tiro.api.routes_export import router as export_router
    from tiro.api.routes_digest_email import router as digest_email_router
    from tiro.api.routes_settings import router as settings_router
    from tiro.api.routes_audio import router as audio_router
    from tiro.api.routes_graph import router as graph_router
    from tiro.api.routes_filters import router as filters_router

    app.include_router(ingest_router)
    app.include_router(articles_router)
    app.include_router(sources_router)
    app.include_router(digest_router)
    app.include_router(digest_email_router)
    app.include_router(search_router)
    app.include_router(classify_router)
    app.include_router(decay_router)
    app.include_router(stats_router)
    app.include_router(export_router)
    app.include_router(settings_router)
    app.include_router(audio_router)
    app.include_router(graph_router)
    app.include_router(filters_router)

    # Static files and templates
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
    # Serve custom themes from library/themes/ if directory exists
    library_themes = config.library / "themes"
    library_themes.mkdir(parents=True, exist_ok=True)
    app.mount("/library/themes", StaticFiles(directory=str(library_themes)), name="library_themes")
    templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

    @app.get("/", response_class=HTMLResponse)
    async def index_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/inbox")

    @app.get("/inbox", response_class=HTMLResponse)
    async def inbox_page(request: Request):
        return templates.TemplateResponse("inbox.html", {"request": request})

    @app.get("/digest", response_class=HTMLResponse)
    async def digest_page(request: Request):
        return templates.TemplateResponse("digest.html", {"request": request})

    @app.get("/articles/{article_id}", response_class=HTMLResponse)
    async def reader(request: Request, article_id: int):
        return templates.TemplateResponse("reader.html", {"request": request, "article_id": article_id})

    @app.get("/stats", response_class=HTMLResponse)
    async def stats_page(request: Request):
        return templates.TemplateResponse("stats.html", {"request": request})

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return templates.TemplateResponse("settings.html", {"request": request})

    @app.get("/graph", response_class=HTMLResponse)
    async def graph_page(request: Request):
        return templates.TemplateResponse("graph.html", {"request": request})

    return app
