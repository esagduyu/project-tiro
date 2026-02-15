"""Reading stats API routes."""

from fastapi import APIRouter, Request

from tiro.stats import get_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def stats(request: Request, period: str = "month"):
    """Get reading stats for the given period (week|month|all)."""
    config = request.app.state.config
    data = get_stats(config, period)
    return {"success": True, "data": data}
