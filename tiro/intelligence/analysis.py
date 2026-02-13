"""On-demand ingenuity/trust analysis using Claude Opus 4.6."""

import json
import logging
import os
from pathlib import Path

import anthropic
import frontmatter

from tiro.config import TiroConfig
from tiro.database import get_connection
from tiro.intelligence.prompts import ingenuity_analysis_prompt

logger = logging.getLogger(__name__)


def get_cached_analysis(config: TiroConfig, article_id: int) -> dict | None:
    """Return cached ingenuity analysis for an article, or None."""
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT ingenuity_analysis FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if row and row["ingenuity_analysis"]:
            return json.loads(row["ingenuity_analysis"])
        return None
    finally:
        conn.close()


def _cache_analysis(config: TiroConfig, article_id: int, analysis: dict) -> None:
    """Store analysis JSON in the article's ingenuity_analysis column."""
    conn = get_connection(config.db_path)
    try:
        conn.execute(
            "UPDATE articles SET ingenuity_analysis = ? WHERE id = ?",
            (json.dumps(analysis), article_id),
        )
        conn.commit()
    finally:
        conn.close()


def _load_article_for_analysis(
    config: TiroConfig, article_id: int
) -> tuple[str, str]:
    """Load article text and source name for analysis.

    Returns (full_text, source_name).
    Raises ValueError if article not found.
    """
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            """SELECT a.markdown_path, s.name AS source_name
               FROM articles a
               LEFT JOIN sources s ON a.source_id = s.id
               WHERE a.id = ?""",
            (article_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found")

        # Read markdown content
        md_path = Path(row["markdown_path"])
        if not md_path.is_absolute():
            md_path = config.articles_dir / md_path
        if not md_path.exists():
            raise ValueError(f"Markdown file not found: {md_path}")

        post = frontmatter.load(str(md_path))
        return post.content, row["source_name"] or "Unknown"
    finally:
        conn.close()


def analyze_article(config: TiroConfig, article_id: int) -> dict:
    """Run ingenuity/trust analysis on an article using Opus 4.6.

    Returns the structured analysis dict.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set — cannot run analysis")

    full_text, source_name = _load_article_for_analysis(config, article_id)

    prompt = ingenuity_analysis_prompt(full_text, source_name)

    logger.info("Running ingenuity analysis for article %d (%s)", article_id, source_name)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.opus_model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    logger.info("Opus analysis response: %d chars", len(raw))

    # Parse JSON — strip markdown fences if Opus wraps them
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove ```json ... ``` wrapper
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    analysis = json.loads(cleaned)

    # Cache the result
    _cache_analysis(config, article_id, analysis)

    return analysis
