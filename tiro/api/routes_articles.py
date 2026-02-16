"""Article API routes."""

import asyncio
import logging
from pathlib import Path

import frontmatter
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tiro.database import get_connection
from tiro.intelligence.analysis import analyze_article, get_cached_analysis
from tiro.stats import update_stat

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
async def list_articles(
    request: Request,
    page: int = 1,
    per_page: int = 0,
    sort: str = "newest",
    is_read: bool | None = None,
    is_vip: bool | None = None,
    ai_tier: str | None = None,
    author: str | None = None,
    source_id: int | None = None,
    tag: str | None = None,
    rating: str | None = None,
    ingestion_method: str | None = None,
    min_reading_time: int | None = None,
    max_reading_time: int | None = None,
    has_audio: bool | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_decayed: bool = True,
    count_only: bool = False,
):
    """List articles with filtering, sorting, and pagination.

    per_page=0 (default) returns all results (backwards compatible).
    count_only=true returns just the count matching filters.
    """
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        where_clauses = []
        params: list = []

        if not include_decayed:
            where_clauses.append("a.relevance_weight >= ?")
            params.append(config.decay_threshold)

        if is_read is not None:
            where_clauses.append("a.is_read = ?")
            params.append(1 if is_read else 0)

        if is_vip is not None:
            where_clauses.append("s.is_vip = ?")
            params.append(1 if is_vip else 0)

        if ai_tier:
            tiers = [t.strip() for t in ai_tier.split(",") if t.strip()]
            if tiers:
                placeholders = ",".join("?" * len(tiers))
                # Handle 'unclassified' as NULL
                if "unclassified" in tiers:
                    tiers_filtered = [t for t in tiers if t != "unclassified"]
                    if tiers_filtered:
                        where_clauses.append(f"(a.ai_tier IN ({','.join('?' * len(tiers_filtered))}) OR a.ai_tier IS NULL)")
                        params.extend(tiers_filtered)
                    else:
                        where_clauses.append("a.ai_tier IS NULL")
                else:
                    where_clauses.append(f"a.ai_tier IN ({placeholders})")
                    params.extend(tiers)

        if author:
            where_clauses.append("a.author = ?")
            params.append(author)

        if source_id is not None:
            where_clauses.append("a.source_id = ?")
            params.append(source_id)

        if tag:
            where_clauses.append("""a.id IN (
                SELECT at2.article_id FROM article_tags at2
                JOIN tags t2 ON t2.id = at2.tag_id
                WHERE t2.name = ?
            )""")
            params.append(tag)

        if rating:
            ratings = [r.strip() for r in rating.split(",") if r.strip()]
            if ratings:
                # Map named ratings to values
                rating_map = {"loved": "2", "liked": "1", "disliked": "-1", "unrated": "NULL"}
                rating_vals = []
                has_unrated = False
                for r in ratings:
                    mapped = rating_map.get(r, r)
                    if mapped == "NULL":
                        has_unrated = True
                    else:
                        rating_vals.append(mapped)

                parts = []
                if rating_vals:
                    parts.append(f"a.rating IN ({','.join('?' * len(rating_vals))})")
                    params.extend(int(v) for v in rating_vals)
                if has_unrated:
                    parts.append("a.rating IS NULL")
                if parts:
                    where_clauses.append(f"({' OR '.join(parts)})")

        if ingestion_method:
            methods = [m.strip() for m in ingestion_method.split(",") if m.strip()]
            if methods:
                placeholders = ",".join("?" * len(methods))
                where_clauses.append(f"COALESCE(a.ingestion_method, 'manual') IN ({placeholders})")
                params.extend(methods)

        if min_reading_time is not None:
            where_clauses.append("a.reading_time_min >= ?")
            params.append(min_reading_time)

        if max_reading_time is not None:
            where_clauses.append("a.reading_time_min <= ?")
            params.append(max_reading_time)

        if has_audio is not None:
            if has_audio:
                where_clauses.append("a.id IN (SELECT article_id FROM audio)")
            else:
                where_clauses.append("a.id NOT IN (SELECT article_id FROM audio)")

        if date_from:
            where_clauses.append("COALESCE(a.published_at, a.ingested_at) >= ?")
            params.append(date_from)

        if date_to:
            where_clauses.append("COALESCE(a.published_at, a.ingested_at) <= ?")
            params.append(date_to + " 23:59:59")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Count only mode (for unread badge etc.)
        if count_only:
            count = conn.execute(
                f"SELECT COUNT(*) FROM articles a LEFT JOIN sources s ON a.source_id = s.id{where_sql}",
                params,
            ).fetchone()[0]
            return {"success": True, "data": {"count": count}}

        # Sort
        sort_sql = {
            "newest": "s.is_vip DESC, COALESCE(a.published_at, a.ingested_at) DESC",
            "oldest": "s.is_vip DESC, COALESCE(a.published_at, a.ingested_at) ASC",
            "importance": """
                CASE a.ai_tier
                    WHEN 'must-read' THEN 0
                    WHEN 'summary-enough' THEN 1
                    WHEN 'discard' THEN 2
                    ELSE 3
                END ASC, s.is_vip DESC, COALESCE(a.published_at, a.ingested_at) DESC
            """,
        }.get(sort, "s.is_vip DESC, COALESCE(a.published_at, a.ingested_at) DESC")

        # Total count for pagination
        total = conn.execute(
            f"SELECT COUNT(*) FROM articles a LEFT JOIN sources s ON a.source_id = s.id{where_sql}",
            params,
        ).fetchone()[0]

        # Pagination
        limit_sql = ""
        if per_page > 0:
            offset = (max(1, page) - 1) * per_page
            limit_sql = f" LIMIT {per_page} OFFSET {offset}"

        query = f"""
            SELECT
                a.id, a.title, a.author, a.url, a.slug, a.summary,
                a.word_count, a.reading_time_min, a.published_at, a.ingested_at,
                a.is_read, a.rating, a.opened_count, a.ai_tier,
                a.relevance_weight, a.ingestion_method,
                s.name AS source_name, s.domain, s.is_vip, s.id AS source_id,
                s.source_type
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            {where_sql}
            ORDER BY {sort_sql}
            {limit_sql}
        """

        rows = conn.execute(query, params).fetchall()

        # Batch-fetch tags for all articles
        article_ids = [row["id"] for row in rows]
        tags_map: dict[int, list[str]] = {aid: [] for aid in article_ids}
        if article_ids:
            placeholders = ",".join("?" * len(article_ids))
            tag_rows = conn.execute(f"""
                SELECT at.article_id, t.name FROM tags t
                JOIN article_tags at ON t.id = at.tag_id
                WHERE at.article_id IN ({placeholders})
            """, article_ids).fetchall()
            for tr in tag_rows:
                tags_map[tr["article_id"]].append(tr["name"])

        articles = []
        for row in rows:
            article = dict(row)
            article["tags"] = tags_map.get(article["id"], [])
            articles.append(article)

        response: dict = {"success": True, "data": articles}
        if per_page > 0:
            import math
            response["pagination"] = {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": math.ceil(total / per_page) if per_page else 1,
            }
        return response
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

        try:
            update_stat(config, "articles_rated")
        except Exception as e:
            logger.error("Failed to update reading stats: %s", e)

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

        # Update reading stats
        try:
            update_stat(config, "articles_read")
            reading_time = conn.execute(
                "SELECT reading_time_min FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
            if reading_time and reading_time["reading_time_min"]:
                update_stat(config, "total_reading_time_min", reading_time["reading_time_min"])
        except Exception as e:
            logger.error("Failed to update reading stats: %s", e)

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
