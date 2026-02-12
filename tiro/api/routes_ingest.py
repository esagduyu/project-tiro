"""Ingestion API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, HttpUrl

from tiro.ingestion.processor import process_article
from tiro.ingestion.web import fetch_and_extract

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


class IngestURLRequest(BaseModel):
    url: HttpUrl


@router.post("/url")
async def ingest_url(body: IngestURLRequest, request: Request):
    """Save a web page by URL."""
    config = request.app.state.config
    url = str(body.url)

    try:
        extracted = await fetch_and_extract(url)
    except Exception as e:
        logger.error("Failed to fetch %s: %s", url, e)
        raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {e}")

    try:
        article = process_article(
            title=extracted["title"],
            author=extracted["author"],
            content_md=extracted["content_md"],
            url=extracted["url"],
            config=config,
        )
    except Exception as e:
        logger.error("Failed to process article from %s: %s", url, e)
        raise HTTPException(status_code=500, detail=f"Failed to process article: {e}")

    return {"success": True, "data": article}
