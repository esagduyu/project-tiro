"""Export API routes for Tiro."""

import asyncio
import logging
import os

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from tiro.export import export_library

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export")
async def export_library_endpoint(
    request: Request,
    tag: str | None = Query(None, description="Filter by tag name"),
    source_id: int | None = Query(None, description="Filter by source ID"),
    rating_min: int | None = Query(None, description="Minimum rating (-1, 1, or 2)"),
    date_from: str | None = Query(None, description="Filter articles ingested after this date (YYYY-MM-DD)"),
):
    """Export the library as a downloadable zip file."""
    config = request.app.state.config

    zip_path = await asyncio.to_thread(
        export_library,
        config,
        tag=tag,
        source_id=source_id,
        rating_min=rating_min,
        date_from=date_from,
    )

    # Build a descriptive filename
    parts = ["tiro-export"]
    if tag:
        parts.append(f"tag-{tag}")
    if source_id:
        parts.append(f"source-{source_id}")
    if rating_min is not None:
        parts.append(f"rating-{rating_min}+")
    if date_from:
        parts.append(f"from-{date_from}")
    filename = "-".join(parts) + ".zip"

    def cleanup(path: str):
        try:
            os.unlink(path)
        except OSError:
            pass

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(cleanup, str(zip_path)),
    )
