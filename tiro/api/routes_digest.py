"""Digest API routes."""

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request

from tiro.intelligence.digest import generate_digest, get_cached_digest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("/today")
async def digest_today(request: Request, refresh: bool = False):
    """Generate or retrieve today's cached digest (all three variants)."""
    config = request.app.state.config
    today = date.today().isoformat()

    # Return cached unless refresh requested
    if not refresh:
        cached = await asyncio.to_thread(get_cached_digest, config, today)
        if cached:
            logger.info("Returning cached digest for %s", today)
            return {"success": True, "data": cached, "cached": True}

    # Generate fresh digest (offloaded to thread — Opus call can take 10-30s)
    try:
        result = await asyncio.to_thread(generate_digest, config)
        return {"success": True, "data": result, "cached": False}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Digest generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Digest generation failed")


@router.get("/today/{digest_type}")
async def digest_by_type(digest_type: str, request: Request, refresh: bool = False):
    """Get a specific digest variant: ranked, by_topic, or by_entity."""
    if digest_type not in ("ranked", "by_topic", "by_entity"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid digest type '{digest_type}'. Must be: ranked, by_topic, by_entity",
        )

    config = request.app.state.config
    today = date.today().isoformat()

    # Return cached unless refresh requested
    if not refresh:
        cached = await asyncio.to_thread(get_cached_digest, config, today, digest_type)
        if cached:
            return {"success": True, "data": cached, "cached": True}

    # Generate all three (Opus generates them together in one prompt)
    try:
        result = await asyncio.to_thread(generate_digest, config)
        if digest_type in result:
            return {"success": True, "data": {digest_type: result[digest_type]}, "cached": False}
        raise HTTPException(status_code=500, detail=f"Digest type '{digest_type}' was not generated")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Digest generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Digest generation failed")
