"""API routes for learned preference classification."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tiro.database import get_connection
from tiro.intelligence.preferences import classify_articles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["classify"])


class ClassifyRequest(BaseModel):
    refresh: Optional[bool] = False


@router.post("/classify")
async def classify(request: Request, body: ClassifyRequest = ClassifyRequest()):
    """Classify unrated articles into tiers using Opus 4.6 learned preferences."""
    config = request.app.state.config

    # If refresh, clear all existing tiers so everything gets reclassified
    if body.refresh:
        conn = get_connection(config.db_path)
        try:
            conn.execute("UPDATE articles SET ai_tier = NULL")
            conn.commit()
            logger.info("Cleared all ai_tier values for reclassification")
        finally:
            conn.close()

    try:
        classifications = await asyncio.to_thread(classify_articles, config)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    return {
        "success": True,
        "data": {
            "classifications": classifications,
            "classified_count": len(classifications),
        },
    }
