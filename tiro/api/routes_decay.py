"""Content decay API routes."""

import logging

from fastapi import APIRouter, Request

from tiro.decay import recalculate_decay

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/decay", tags=["decay"])


@router.post("/recalculate")
async def recalculate(request: Request):
    """Manually trigger decay recalculation for all articles."""
    config = request.app.state.config
    result = recalculate_decay(config)
    return {"success": True, "data": result}
