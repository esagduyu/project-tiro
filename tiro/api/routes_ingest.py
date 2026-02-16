"""Ingestion API routes."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, HttpUrl

from tiro.database import get_connection
from tiro.ingestion.email import parse_eml
from tiro.ingestion.imap import check_imap_inbox
from tiro.ingestion.processor import process_article
from tiro.ingestion.web import fetch_and_extract

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


@router.get("/check")
async def check_url(request: Request, url: str):
    """Check if a URL is already saved. Returns article data if found."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        existing = conn.execute(
            "SELECT a.id, a.title, a.ingested_at, s.name as source_name "
            "FROM articles a LEFT JOIN sources s ON a.source_id = s.id "
            "WHERE a.url = ?",
            (url,),
        ).fetchone()
    finally:
        conn.close()

    if existing:
        return {
            "success": True,
            "saved": True,
            "data": {
                "id": existing["id"],
                "title": existing["title"],
                "source": existing["source_name"],
                "ingested_at": existing["ingested_at"],
            },
        }
    return {"success": True, "saved": False}


class IngestURLRequest(BaseModel):
    url: HttpUrl
    ingestion_method: str = "manual"


@router.post("/url")
async def ingest_url(body: IngestURLRequest, request: Request):
    """Save a web page by URL."""
    config = request.app.state.config
    url = str(body.url)

    # Duplicate check
    conn = get_connection(config.db_path)
    try:
        existing = conn.execute(
            "SELECT a.id, a.title, a.ingested_at, s.name as source_name "
            "FROM articles a LEFT JOIN sources s ON a.source_id = s.id "
            "WHERE a.url = ?",
            (url,),
        ).fetchone()
    finally:
        conn.close()
    if existing:
        logger.info("Duplicate URL skipped: '%s' already saved as article %d", existing["title"], existing["id"])
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "already_saved",
                "data": {
                    "id": existing["id"],
                    "title": existing["title"],
                    "source": existing["source_name"],
                    "ingested_at": existing["ingested_at"],
                },
            },
        )

    try:
        extracted = await fetch_and_extract(url)
    except Exception as e:
        logger.error("Failed to fetch %s: %s", url, e)
        raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {e}")

    try:
        article = await asyncio.to_thread(
            process_article,
            title=extracted["title"],
            author=extracted["author"],
            content_md=extracted["content_md"],
            url=extracted["url"],
            config=config,
            ingestion_method=body.ingestion_method,
        )
    except Exception as e:
        logger.error("Failed to process article from %s: %s", url, e)
        raise HTTPException(status_code=500, detail=f"Failed to process article: {e}")

    return {"success": True, "data": article}


@router.post("/email")
async def ingest_email(file: UploadFile, request: Request):
    """Save a newsletter from an uploaded .eml file."""
    config = request.app.state.config

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        extracted = await asyncio.to_thread(parse_eml, raw)
    except ValueError as e:
        logger.error("Failed to parse email: %s", e)
        raise HTTPException(status_code=422, detail=f"Failed to parse email: {e}")
    except Exception as e:
        logger.error("Failed to parse email: %s", e)
        raise HTTPException(status_code=422, detail=f"Failed to parse email: {e}")

    # Duplicate check by title + sender
    conn = get_connection(config.db_path)
    try:
        existing = conn.execute(
            "SELECT a.id, a.title FROM articles a "
            "JOIN sources s ON a.source_id = s.id "
            "WHERE a.title = ? AND s.email_sender = ?",
            (extracted["title"], extracted["email_sender"]),
        ).fetchone()
    finally:
        conn.close()
    if existing:
        logger.info("Duplicate email skipped: '%s' already saved as article %d", existing["title"], existing["id"])
        raise HTTPException(status_code=409, detail=f"Article already saved: \"{existing['title']}\" (id={existing['id']})")

    try:
        article = await asyncio.to_thread(
            process_article,
            title=extracted["title"],
            author=extracted["author"],
            content_md=extracted["content_md"],
            url=extracted["url"],
            config=config,
            published_at=extracted["published_at"],
            email_sender=extracted["email_sender"],
            ingestion_method="email",
        )
    except Exception as e:
        logger.error("Failed to process email article: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to process email: {e}")

    return {"success": True, "data": article}


class BatchEmailRequest(BaseModel):
    path: str


@router.post("/batch-email")
async def ingest_batch_email(body: BatchEmailRequest, request: Request):
    """Process all .eml files in a directory."""
    config = request.app.state.config
    directory = Path(body.path)

    if not directory.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {body.path}")

    eml_files = sorted(directory.glob("*.eml"))
    if not eml_files:
        raise HTTPException(status_code=400, detail=f"No .eml files found in {body.path}")

    results = {"processed": [], "skipped": [], "failed": []}

    for eml_path in eml_files:
        filename = eml_path.name
        try:
            extracted = parse_eml(eml_path)
        except (ValueError, Exception) as e:
            logger.error("Failed to parse %s: %s", filename, e)
            results["failed"].append({"file": filename, "error": str(e)})
            continue

        # Duplicate check
        conn = get_connection(config.db_path)
        try:
            existing = conn.execute(
                "SELECT a.id, a.title FROM articles a "
                "JOIN sources s ON a.source_id = s.id "
                "WHERE a.title = ? AND s.email_sender = ?",
                (extracted["title"], extracted["email_sender"]),
            ).fetchone()
        finally:
            conn.close()

        if existing:
            logger.info("Duplicate email skipped: '%s'", filename)
            results["skipped"].append({"file": filename, "title": existing["title"]})
            continue

        try:
            article = process_article(
                title=extracted["title"],
                author=extracted["author"],
                content_md=extracted["content_md"],
                url=extracted["url"],
                config=config,
                published_at=extracted["published_at"],
                email_sender=extracted["email_sender"],
                ingestion_method="email",
            )
            results["processed"].append({"file": filename, "id": article["id"], "title": article["title"]})
        except Exception as e:
            logger.error("Failed to process %s: %s", filename, e)
            results["failed"].append({"file": filename, "error": str(e)})

    return {
        "success": True,
        "data": {
            "total": len(eml_files),
            "processed": len(results["processed"]),
            "skipped": len(results["skipped"]),
            "failed": len(results["failed"]),
            "details": results,
        },
    }


@router.post("/imap")
async def ingest_imap(request: Request):
    """Check IMAP inbox for new newsletters and ingest them."""
    config = request.app.state.config

    if not config.imap_user or not config.imap_password:
        raise HTTPException(
            status_code=400,
            detail="IMAP not configured. Set imap_user and imap_password in config.yaml or use Settings.",
        )

    try:
        result = await asyncio.to_thread(check_imap_inbox, config)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {"success": True, "data": result}
