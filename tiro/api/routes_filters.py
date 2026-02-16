"""Filter facet counts API."""

import logging

from fastapi import APIRouter, Request

from tiro.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/filters", tags=["filters"])


@router.get("")
async def get_filter_counts(request: Request):
    """Return counts for all filter facets (for the filter panel UI)."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        data: dict = {}

        # Read status
        data["read_status"] = {
            "read": conn.execute("SELECT COUNT(*) FROM articles WHERE is_read=1").fetchone()[0],
            "unread": conn.execute("SELECT COUNT(*) FROM articles WHERE is_read=0").fetchone()[0],
        }

        # AI tiers
        data["tiers"] = [
            dict(r) for r in conn.execute(
                "SELECT COALESCE(ai_tier, 'unclassified') as name, COUNT(*) as count "
                "FROM articles GROUP BY ai_tier"
            ).fetchall()
        ]

        # Sources (with VIP flag)
        data["sources"] = [
            dict(r) for r in conn.execute(
                """SELECT s.id, s.name, s.is_vip, COUNT(a.id) as count
                   FROM sources s LEFT JOIN articles a ON s.id = a.source_id
                   GROUP BY s.id ORDER BY count DESC"""
            ).fetchall()
        ]

        # Authors
        data["authors"] = [
            dict(r) for r in conn.execute(
                """SELECT author as name, COUNT(*) as count FROM articles
                   WHERE author IS NOT NULL AND author != ''
                   GROUP BY author ORDER BY count DESC"""
            ).fetchall()
        ]

        # Tags
        data["tags"] = [
            dict(r) for r in conn.execute(
                """SELECT t.name, COUNT(at.article_id) as count
                   FROM tags t JOIN article_tags at ON t.id = at.tag_id
                   GROUP BY t.id ORDER BY count DESC"""
            ).fetchall()
        ]

        # Ingestion methods
        data["ingestion_methods"] = [
            dict(r) for r in conn.execute(
                "SELECT COALESCE(ingestion_method, 'manual') as name, COUNT(*) as count "
                "FROM articles GROUP BY ingestion_method"
            ).fetchall()
        ]

        # Ratings
        data["ratings"] = [
            dict(r) for r in conn.execute(
                """SELECT CASE rating
                       WHEN 2 THEN 'loved' WHEN 1 THEN 'liked'
                       WHEN -1 THEN 'disliked' ELSE 'unrated'
                   END as name, COUNT(*) as count
                   FROM articles GROUP BY rating"""
            ).fetchall()
        ]

        # Reading time ranges
        data["reading_time"] = {
            "quick": conn.execute("SELECT COUNT(*) FROM articles WHERE reading_time_min < 5").fetchone()[0],
            "medium": conn.execute("SELECT COUNT(*) FROM articles WHERE reading_time_min BETWEEN 5 AND 15").fetchone()[0],
            "long": conn.execute("SELECT COUNT(*) FROM articles WHERE reading_time_min > 15").fetchone()[0],
        }

        # Has audio
        data["has_audio"] = conn.execute("SELECT COUNT(*) FROM audio").fetchone()[0]

        # Total articles
        data["total"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

        return {"success": True, "data": data}
    finally:
        conn.close()
