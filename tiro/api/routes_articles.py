"""Article API routes."""

import logging
from pathlib import Path

import frontmatter
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tiro.database import get_connection

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
                a.is_read, a.rating, a.opened_count, a.markdown_path,
                s.name AS source_name, s.domain, s.is_vip, s.id AS source_id
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
async def list_articles(request: Request):
    """List all articles, VIP pinned to top, newest first."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute("""
            SELECT
                a.id, a.title, a.author, a.url, a.slug, a.summary,
                a.word_count, a.reading_time_min, a.published_at, a.ingested_at,
                a.is_read, a.rating, a.opened_count,
                s.name AS source_name, s.domain, s.is_vip, s.id AS source_id
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            ORDER BY s.is_vip DESC, a.ingested_at DESC
        """).fetchall()

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
