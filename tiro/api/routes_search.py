"""Search and related articles API routes."""

import asyncio
import logging

from fastapi import APIRouter, Query, Request

from tiro.search.semantic import (
    find_related_articles,
    generate_connection_notes,
    get_related_articles,
    search_articles,
    store_relations,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(request: Request, q: str = Query(..., min_length=1)):
    """Semantic search across all articles."""
    config = request.app.state.config
    results = await asyncio.to_thread(search_articles, q, config)
    return {"success": True, "data": results}


@router.get("/articles/{article_id}/related")
async def related_articles(request: Request, article_id: int):
    """Get related articles for a given article."""
    config = request.app.state.config
    results = await asyncio.to_thread(get_related_articles, article_id, config)
    return {"success": True, "data": results}


@router.post("/recompute-relations")
async def recompute_relations(request: Request):
    """Recompute related articles for all existing articles."""
    config = request.app.state.config

    def _recompute():
        from tiro.database import get_connection

        conn = get_connection(config.db_path)
        try:
            rows = conn.execute(
                "SELECT id, title, summary FROM articles ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        count = 0
        for row in rows:
            try:
                relations = find_related_articles(row["id"], config, limit=5)
                if relations:
                    generate_connection_notes(
                        row["summary"] or "", row["title"], relations, config
                    )
                    store_relations(row["id"], relations, config)
                    count += 1
            except Exception as e:
                logger.error("Recompute failed for article %d: %s", row["id"], e)
        return count

    count = await asyncio.to_thread(_recompute)
    return {"success": True, "data": {"articles_processed": count}}
