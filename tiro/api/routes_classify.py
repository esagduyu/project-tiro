"""API routes for learned preference classification."""

import asyncio
import logging

from fastapi import APIRouter, Request

from tiro.intelligence.preferences import classify_articles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["classify"])


@router.post("/classify")
async def classify(request: Request):
    """Classify unrated articles into tiers using Opus 4.6 learned preferences."""
    config = request.app.state.config

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
