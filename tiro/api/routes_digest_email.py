"""Digest email delivery API routes."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from tiro.intelligence.email_digest import send_digest_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.post("/send")
async def send_digest(request: Request):
    """Send today's digest via email."""
    config = request.app.state.config

    try:
        result = await asyncio.to_thread(send_digest_email, config)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Failed to send digest email: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send digest email")
