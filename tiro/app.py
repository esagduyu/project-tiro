"""FastAPI application for Tiro."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tiro.config import TiroConfig, load_config
from tiro.database import init_db
from tiro.decay import recalculate_decay
from tiro.vectorstore import init_vectorstore

logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and vectorstore on startup."""
    config: TiroConfig = app.state.config

    # Ensure library directories exist
    config.articles_dir.mkdir(parents=True, exist_ok=True)

    # Initialize SQLite
    init_db(config.db_path)

    # Initialize ChromaDB with configured embedding model
    init_vectorstore(config.chroma_dir, config.default_embedding_model)

    # Recalculate content decay weights
    recalculate_decay(config)

    logger.info("Tiro is ready — library at %s", config.library)
    yield


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

    # Static files and templates
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
    templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    @app.get("/articles/{article_id}", response_class=HTMLResponse)
    async def reader(request: Request, article_id: int):
        return templates.TemplateResponse("reader.html", {"request": request, "article_id": article_id})

    @app.get("/stats", response_class=HTMLResponse)
    async def stats_page(request: Request):
        return templates.TemplateResponse("stats.html", {"request": request})

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        return templates.TemplateResponse("settings.html", {"request": request})

    return app
