"""Article API routes."""

import asyncio
import logging
from pathlib import Path

import frontmatter
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tiro.database import get_connection
from tiro.intelligence.analysis import analyze_article, get_cached_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("/{article_id}")
async def get_article(article_id: int, request: Request):
    """Get a single article with full markdown content."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        row = conn.execute("""
            SELECT
                a.id, a.title, a.author, a.url, a.slug, a.summary,
                a.word_count, a.reading_time_min, a.published_at, a.ingested_at,
                a.is_read, a.rating, a.opened_count, a.markdown_path, a.ai_tier,
                a.relevance_weight,
                s.name AS source_name, s.domain, s.is_vip, s.id AS source_id,
                s.source_type
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.id = ?
        """, (article_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Article not found")

        article = dict(row)

        # Fetch tags
        tags = conn.execute("""
            SELECT t.name FROM tags t
            JOIN article_tags at ON t.id = at.tag_id
            WHERE at.article_id = ?
        """, (article_id,)).fetchall()
        article["tags"] = [t["name"] for t in tags]

        # Read markdown content from file
        md_path = Path(article["markdown_path"])
        if not md_path.is_absolute():
            md_path = config.articles_dir / md_path
        if md_path.exists():
            post = frontmatter.load(str(md_path))
            article["content"] = post.content
        else:
            article["content"] = ""
            logger.warning("Markdown file not found: %s", md_path)

        return {"success": True, "data": article}
    finally:
        conn.close()


@router.get("")
async def list_articles(request: Request, include_decayed: bool = True):
    """List all articles, VIP pinned to top, newest first.

    ?include_decayed=false hides articles with relevance_weight below the decay threshold.
    """
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        query = """
            SELECT
                a.id, a.title, a.author, a.url, a.slug, a.summary,
                a.word_count, a.reading_time_min, a.published_at, a.ingested_at,
                a.is_read, a.rating, a.opened_count, a.ai_tier,
                a.relevance_weight,
                s.name AS source_name, s.domain, s.is_vip, s.id AS source_id,
                s.source_type
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
        """
        params = []
        if not include_decayed:
            query += " WHERE a.relevance_weight >= ?"
            params.append(config.decay_threshold)
        query += " ORDER BY s.is_vip DESC, a.ingested_at DESC"

        rows = conn.execute(query, params).fetchall()

        articles = []
        for row in rows:
            article = dict(row)
            tags = conn.execute("""
                SELECT t.name FROM tags t
                JOIN article_tags at ON t.id = at.tag_id
                WHERE at.article_id = ?
            """, (article["id"],)).fetchall()
            article["tags"] = [t["name"] for t in tags]
            articles.append(article)

        return {"success": True, "data": articles}
    finally:
        conn.close()


class RateRequest(BaseModel):
    rating: int


@router.patch("/{article_id}/rate")
async def rate_article(article_id: int, body: RateRequest, request: Request):
    """Set article rating: -1 (dislike), 1 (like), 2 (love)."""
    if body.rating not in (-1, 1, 2):
        raise HTTPException(status_code=400, detail="Rating must be -1, 1, or 2")

    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        cursor = conn.execute(
            "UPDATE articles SET rating = ? WHERE id = ?",
            (body.rating, article_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Article not found")
        conn.commit()
        return {"success": True, "data": {"id": article_id, "rating": body.rating}}
    finally:
        conn.close()


@router.patch("/{article_id}/read")
async def mark_read(article_id: int, request: Request):
    """Mark article as read and increment open count."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        cursor = conn.execute(
            "UPDATE articles SET is_read = 1, opened_count = opened_count + 1 WHERE id = ?",
            (article_id,),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Article not found")
        conn.commit()
        row = conn.execute(
            "SELECT is_read, opened_count FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        return {
            "success": True,
            "data": {
                "id": article_id,
                "is_read": row["is_read"],
                "opened_count": row["opened_count"],
            },
        }
    finally:
        conn.close()


@router.get("/{article_id}/analysis")
async def get_analysis(
    article_id: int,
    request: Request,
    refresh: bool = False,
    cache_only: bool = False,
):
    """Get or trigger ingenuity/trust analysis for an article."""
    config = request.app.state.config

    # Return cached unless refresh requested
    if not refresh:
        cached = get_cached_analysis(config, article_id)
        if cached:
            return {"success": True, "data": cached}

    # If cache_only, don't trigger a new analysis
    if cache_only:
        return {"success": True, "data": None}

    # Run Opus analysis (blocking call wrapped in thread)
    try:
        analysis = await asyncio.to_thread(analyze_article, config, article_id)
        return {"success": True, "data": analysis}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Analysis failed for article %d: %s", article_id, e)
        raise HTTPException(status_code=500, detail="Analysis failed")
