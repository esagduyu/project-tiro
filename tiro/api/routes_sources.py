"""Source management API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request

from tiro.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
async def list_sources(request: Request):
    """List all sources with article counts."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute("""
            SELECT s.id, s.name, s.domain, s.email_sender, s.source_type,
                   s.is_vip, COUNT(a.id) AS article_count
            FROM sources s
            LEFT JOIN articles a ON s.id = a.source_id
            GROUP BY s.id
            ORDER BY s.is_vip DESC, s.name ASC
        """).fetchall()

        return {"success": True, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.patch("/{source_id}/vip")
async def toggle_vip(source_id: int, request: Request):
    """Toggle VIP status for a source."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT is_vip FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Source not found")

        new_vip = not bool(row["is_vip"])
        conn.execute(
            "UPDATE sources SET is_vip = ? WHERE id = ?", (new_vip, source_id)
        )
        conn.commit()

        return {"success": True, "data": {"id": source_id, "is_vip": new_vip}}
    finally:
        conn.close()
