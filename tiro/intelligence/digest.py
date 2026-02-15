"""Daily digest generation using Claude Opus 4.6."""

import json
import logging
import os
import re
from datetime import date, datetime, timezone

import anthropic

from tiro.config import TiroConfig
from tiro.database import get_connection
from tiro.intelligence.prompts import daily_digest_prompt

logger = logging.getLogger(__name__)

RATING_LABELS = {-1: "Dislike", 1: "Like", 2: "Love"}
DIGEST_TYPES = ("ranked", "by_topic", "by_entity")

# Section header patterns to split Opus's response into three digest types
SECTION_PATTERNS = [
    (r"###?\s*1[\.\):]?\s*Ranked\s+by\s+Importance", "ranked"),
    (r"###?\s*2[\.\):]?\s*Grouped\s+by\s+Topic", "by_topic"),
    (r"###?\s*3[\.\):]?\s*Grouped\s+by\s+Entity", "by_entity"),
]


MAX_ARTICLES_FOR_DIGEST = 50  # cap to avoid enormous prompts


def _gather_articles(config: TiroConfig) -> tuple[list[dict], list[str], list[dict]]:
    """Gather recent articles, VIP source names, and recent ratings from the database.

    Returns (articles, vip_sources, recent_ratings).
    """
    conn = get_connection(config.db_path)
    try:
        # Get recent articles with source info (capped to avoid huge prompts)
        rows = conn.execute("""
            SELECT
                a.id, a.title, a.summary, a.published_at, a.ingested_at,
                a.is_read, a.rating, a.relevance_weight,
                s.name AS source_name, s.is_vip
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            ORDER BY a.ingested_at DESC
            LIMIT ?
        """, (MAX_ARTICLES_FOR_DIGEST,)).fetchall()

        if not rows:
            return [], [], []

        article_ids = [row["id"] for row in rows]

        # Batch-fetch all tags for these articles
        placeholders = ",".join("?" * len(article_ids))
        tag_rows = conn.execute(f"""
            SELECT at.article_id, t.name
            FROM article_tags at JOIN tags t ON t.id = at.tag_id
            WHERE at.article_id IN ({placeholders})
        """, article_ids).fetchall()
        tags_by_article: dict[int, list[str]] = {}
        for row in tag_rows:
            tags_by_article.setdefault(row["article_id"], []).append(row["name"])

        # Batch-fetch all entities for these articles
        entity_rows = conn.execute(f"""
            SELECT ae.article_id, e.name
            FROM article_entities ae JOIN entities e ON e.id = ae.entity_id
            WHERE ae.article_id IN ({placeholders})
        """, article_ids).fetchall()
        entities_by_article: dict[int, list[str]] = {}
        for row in entity_rows:
            entities_by_article.setdefault(row["article_id"], []).append(row["name"])

        articles = []
        recent_ratings = []

        for row in rows:
            aid = row["id"]

            articles.append({
                "id": aid,
                "title": row["title"],
                "source": row["source_name"] or "Unknown",
                "is_vip": bool(row["is_vip"]),
                "tags": tags_by_article.get(aid, []),
                "entities": entities_by_article.get(aid, []),
                "summary": row["summary"] or "",
                "published_date": row["published_at"] or row["ingested_at"],
                "relevance_weight": row["relevance_weight"] or 1.0,
            })

            # Collect rated articles for context
            if row["rating"] is not None:
                recent_ratings.append({
                    "title": row["title"],
                    "source": row["source_name"] or "Unknown",
                    "rating_label": RATING_LABELS.get(row["rating"], "Unknown"),
                    "summary": row["summary"] or "",
                })

        # Get VIP sources
        vip_rows = conn.execute(
            "SELECT name FROM sources WHERE is_vip = 1"
        ).fetchall()
        vip_sources = [r["name"] for r in vip_rows]

        return articles, vip_sources, recent_ratings
    finally:
        conn.close()


def _split_digest(content: str) -> dict[str, str]:
    """Split Opus's combined response into three digest sections.

    Returns dict mapping digest_type -> markdown content.
    """
    # Find positions of each section header
    positions = []
    for pattern, dtype in SECTION_PATTERNS:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            positions.append((match.start(), match.end(), dtype))

    # Sort by position
    positions.sort(key=lambda x: x[0])

    result = {}
    for i, (start, header_end, dtype) in enumerate(positions):
        # Content runs from after the header to the start of the next section (or end)
        if i + 1 < len(positions):
            section_content = content[header_end : positions[i + 1][0]]
        else:
            section_content = content[header_end:]

        result[dtype] = section_content.strip()

    # Fallback: if splitting failed, put everything in ranked
    if not result:
        logger.warning("Could not split digest into sections, using full content as ranked")
        result["ranked"] = content.strip()

    return result


def _cache_digest(
    config: TiroConfig,
    today: str,
    sections: dict[str, str],
    article_ids: list[int],
) -> None:
    """Cache digest sections in the SQLite digests table."""
    conn = get_connection(config.db_path)
    try:
        ids_json = json.dumps(article_ids)
        for dtype, content in sections.items():
            conn.execute(
                """INSERT OR REPLACE INTO digests (date, digest_type, content, article_ids)
                   VALUES (?, ?, ?, ?)""",
                (today, dtype, content, ids_json),
            )
        conn.commit()
        logger.info("Cached %d digest sections for %s", len(sections), today)
    finally:
        conn.close()


def get_cached_digest(config: TiroConfig, today: str, digest_type: str | None = None) -> dict | None:
    """Retrieve cached digest from SQLite.

    Looks for today's digest first, then falls back to the most recent cached
    digest (so a digest generated last night isn't lost at midnight).

    Returns dict mapping digest_type -> content, or None if not cached.
    If digest_type is specified, returns only that type.
    """
    conn = get_connection(config.db_path)
    try:
        if digest_type:
            # Try today first, then most recent
            row = conn.execute(
                """SELECT content, article_ids, created_at FROM digests
                   WHERE digest_type = ?
                   ORDER BY CASE WHEN date = ? THEN 0 ELSE 1 END, date DESC
                   LIMIT 1""",
                (digest_type, today),
            ).fetchone()
            if row:
                return {
                    digest_type: {
                        "content": row["content"],
                        "article_ids": json.loads(row["article_ids"]),
                        "created_at": row["created_at"],
                    }
                }
            return None
        else:
            # Try today first
            rows = conn.execute(
                "SELECT digest_type, content, article_ids, created_at FROM digests WHERE date = ?",
                (today,),
            ).fetchall()
            # Fall back to most recent date
            if not rows:
                rows = conn.execute(
                    """SELECT digest_type, content, article_ids, created_at FROM digests
                       WHERE date = (SELECT MAX(date) FROM digests)""",
                ).fetchall()
            if not rows:
                return None
            return {
                row["digest_type"]: {
                    "content": row["content"],
                    "article_ids": json.loads(row["article_ids"]),
                    "created_at": row["created_at"],
                }
                for row in rows
            }
    finally:
        conn.close()


def generate_digest(config: TiroConfig) -> dict:
    """Generate today's digest using Opus 4.6.

    Returns dict mapping digest_type -> {"content": str, "article_ids": list[int], "created_at": str}.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot generate digest")

    articles, vip_sources, recent_ratings = _gather_articles(config)

    if not articles:
        raise ValueError("No articles in library — save some articles first")

    # Build prompt
    prompt = daily_digest_prompt(vip_sources, recent_ratings, articles)
    article_ids = [a["id"] for a in articles]

    logger.info(
        "Generating digest with %d articles (%d VIP sources, %d rated)",
        len(articles),
        len(vip_sources),
        len(recent_ratings),
    )

    # Call Opus 4.6
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.opus_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_content = response.content[0].text
    logger.info("Opus digest response: %d chars", len(raw_content))

    # Split into sections
    sections = _split_digest(raw_content)

    # Ensure all three types exist
    for dtype in DIGEST_TYPES:
        if dtype not in sections:
            sections[dtype] = "*This section was not generated. Try refreshing the digest.*"

    # Cache
    today = date.today().isoformat()
    _cache_digest(config, today, sections, article_ids)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return {
        dtype: {
            "content": content,
            "article_ids": article_ids,
            "created_at": now,
        }
        for dtype, content in sections.items()
    }
