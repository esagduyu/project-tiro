"""Learned preferences — classify unrated articles using Opus 4.6."""

import json
import logging
import os

import anthropic

from tiro.config import TiroConfig
from tiro.database import get_connection
from tiro.intelligence.prompts import learned_preferences_prompt

logger = logging.getLogger(__name__)

MAX_UNRATED_FOR_CLASSIFICATION = 50  # cap to avoid enormous prompts
MIN_RATED_ARTICLES = 5  # minimum rated articles needed before classification


def _gather_rated_articles(config: TiroConfig) -> tuple[list[dict], list[dict], list[dict]]:
    """Gather rated articles grouped by rating.

    Returns (loved, liked, disliked) — each a list of dicts with title, source, summary.
    """
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute("""
            SELECT a.title, a.summary, a.rating,
                   s.name AS source_name
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.rating IS NOT NULL
            ORDER BY a.ingested_at DESC
        """).fetchall()

        loved = []
        liked = []
        disliked = []

        for row in rows:
            entry = {
                "title": row["title"],
                "source": row["source_name"] or "Unknown",
                "summary": row["summary"] or "",
            }
            if row["rating"] == 2:
                loved.append(entry)
            elif row["rating"] == 1:
                liked.append(entry)
            elif row["rating"] == -1:
                disliked.append(entry)

        return loved, liked, disliked
    finally:
        conn.close()


def _gather_vip_sources(config: TiroConfig) -> list[str]:
    """Get names of VIP sources."""
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sources WHERE is_vip = 1"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()


def _gather_unrated_articles(config: TiroConfig) -> list[dict]:
    """Gather unrated articles (ai_tier IS NULL) for classification.

    Returns list of dicts with id, title, source, summary.
    Capped at MAX_UNRATED_FOR_CLASSIFICATION.
    """
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute("""
            SELECT a.id, a.title, a.summary,
                   s.name AS source_name
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
            WHERE a.ai_tier IS NULL
            ORDER BY a.ingested_at DESC
            LIMIT ?
        """, (MAX_UNRATED_FOR_CLASSIFICATION,)).fetchall()

        return [
            {
                "id": row["id"],
                "title": row["title"],
                "source": row["source_name"] or "Unknown",
                "summary": row["summary"] or "",
            }
            for row in rows
        ]
    finally:
        conn.close()


def _update_article_tiers(config: TiroConfig, classifications: list[dict]) -> None:
    """Update ai_tier column for each classified article."""
    valid_tiers = {"must-read", "summary-enough", "discard"}
    conn = get_connection(config.db_path)
    try:
        for c in classifications:
            tier = c.get("tier")
            article_id = c.get("article_id")
            if tier not in valid_tiers:
                logger.warning(
                    "Skipping invalid tier %r for article %s", tier, article_id
                )
                continue
            conn.execute(
                "UPDATE articles SET ai_tier = ? WHERE id = ?",
                (tier, article_id),
            )
        conn.commit()
        logger.info("Updated ai_tier for %d articles", len(classifications))
    finally:
        conn.close()


def classify_articles(config: TiroConfig) -> list[dict]:
    """Classify unrated articles using learned preferences via Opus 4.6.

    Gathers rated articles (loved/liked/disliked), VIP sources, and unrated
    articles, then calls Opus to classify each unrated article into a tier:
    must-read, summary-enough, or discard.

    Requires at least MIN_RATED_ARTICLES rated articles to have enough signal.

    Returns list of classification dicts: [{"article_id": int, "tier": str, "reason": str}, ...]
    Raises ValueError if not enough rated articles or no unrated articles.
    Raises RuntimeError if ANTHROPIC_API_KEY is not set.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot classify articles")

    # Gather data
    loved, liked, disliked = _gather_rated_articles(config)
    total_rated = len(loved) + len(liked) + len(disliked)

    if total_rated < MIN_RATED_ARTICLES:
        raise ValueError("Need at least 5 rated articles")

    vip_sources = _gather_vip_sources(config)
    unrated = _gather_unrated_articles(config)

    if not unrated:
        raise ValueError("No unrated articles to classify")

    # Build prompt
    prompt = learned_preferences_prompt(
        loved_articles=loved,
        liked_articles=liked,
        disliked_articles=disliked,
        vip_sources=vip_sources,
        unrated_articles=unrated,
    )

    logger.info(
        "Classifying %d unrated articles (rated: %d loved, %d liked, %d disliked, %d VIP sources)",
        len(unrated),
        len(loved),
        len(liked),
        len(disliked),
        len(vip_sources),
    )

    # Call Opus 4.6
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.opus_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    logger.info("Opus classification response: %d chars", len(raw))

    # Parse JSON — strip markdown fences if Opus wraps them
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )

    result = json.loads(cleaned)
    classifications = result.get("classifications", [])

    # Update database
    _update_article_tiers(config, classifications)

    return classifications
