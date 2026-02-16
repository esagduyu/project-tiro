"""Tiro MCP server — exposes the reading library to Claude Desktop and Claude Code."""

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import frontmatter
from mcp.server.fastmcp import FastMCP

from tiro.config import TiroConfig, load_config
from tiro.database import get_connection
from tiro.vectorstore import init_vectorstore, get_collection

logger = logging.getLogger(__name__)

mcp = FastMCP("Tiro Reading Library")

# Module-level config, initialized in main()
_config: TiroConfig | None = None


def _get_config() -> TiroConfig:
    global _config
    if _config is None:
        _config = load_config()
        # Initialize ChromaDB so get_collection() works
        init_vectorstore(_config.chroma_dir, _config.default_embedding_model)
    return _config


def _format_articles(rows, tags_map, score_map=None) -> str:
    """Format article rows into readable text output."""
    lines = []
    for r in rows:
        r = dict(r) if not isinstance(r, dict) else r
        aid = r["id"]
        vip = " [VIP]" if r.get("is_vip") else ""
        tags = ", ".join(tags_map.get(aid, []))
        rating_label = {-1: "👎", 1: "👍", 2: "❤️"}.get(r.get("rating"), "")
        tier = f" [{r['ai_tier']}]" if r.get("ai_tier") else ""
        score_str = f", similarity: {score_map[aid]:.0%}" if score_map and aid in score_map else ""
        lines.append(
            f"- **{r['title']}** (ID: {aid}{score_str}){vip}{tier} {rating_label}\n"
            f"  Source: {r.get('source_name') or 'Unknown'} | "
            f"{r.get('reading_time_min') or '?'} min read | "
            f"Tags: {tags or 'none'}\n"
            f"  Summary: {r.get('summary') or 'No summary'}\n"
        )
    return "\n".join(lines)


def _batch_fetch_tags(conn, article_ids) -> dict[int, list[str]]:
    """Fetch tags for a list of article IDs."""
    if not article_ids:
        return {}
    placeholders = ",".join("?" * len(article_ids))
    tag_rows = conn.execute(
        f"""SELECT at.article_id, t.name
            FROM article_tags at
            JOIN tags t ON at.tag_id = t.id
            WHERE at.article_id IN ({placeholders})""",
        article_ids,
    ).fetchall()
    tags_map: dict[int, list[str]] = {}
    for tr in tag_rows:
        tags_map.setdefault(tr["article_id"], []).append(tr["name"])
    return tags_map


def _build_filter_sql(
    *,
    author: str = "",
    source: str = "",
    tag: str = "",
    ai_tier: str = "",
    is_unread: bool | None = None,
    is_vip: bool | None = None,
    rating_min: int | None = None,
    date_from: str = "",
    date_to: str = "",
    ingestion_method: str = "",
    article_ids: list[int] | None = None,
) -> tuple[str, list]:
    """Build WHERE clause and params from filter arguments."""
    conditions = []
    params: list = []

    if article_ids is not None:
        placeholders = ",".join("?" * len(article_ids))
        conditions.append(f"a.id IN ({placeholders})")
        params.extend(article_ids)

    if is_unread is not None:
        conditions.append("a.is_read = ?")
        params.append(0 if is_unread else 1)

    if ai_tier:
        conditions.append("a.ai_tier = ?")
        params.append(ai_tier)

    if rating_min is not None:
        conditions.append("a.rating >= ?")
        params.append(rating_min)

    if ingestion_method:
        conditions.append("a.ingestion_method = ?")
        params.append(ingestion_method)

    if date_from:
        conditions.append("COALESCE(a.published_at, a.ingested_at) >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("COALESCE(a.published_at, a.ingested_at) <= ?")
        params.append(date_to + " 23:59:59")

    if is_vip is not None:
        conditions.append("s.is_vip = ?")
        params.append(1 if is_vip else 0)

    if source:
        conditions.append("(s.name LIKE ? OR s.domain LIKE ?)")
        params.extend([f"%{source}%", f"%{source}%"])

    if author:
        conditions.append("a.author LIKE ?")
        params.append(f"%{author}%")

    where = " AND ".join(conditions) if conditions else "1=1"

    # Tag filter requires a JOIN
    tag_join = ""
    if tag:
        tag_join = " JOIN article_tags at_f ON a.id = at_f.article_id JOIN tags t_f ON at_f.tag_id = t_f.id"
        where += " AND t_f.name = ?"
        params.append(tag.lower().strip())

    return where, params, tag_join


@mcp.tool()
def search_articles(
    query: str = "",
    author: str = "",
    source: str = "",
    tag: str = "",
    ai_tier: str = "",
    is_unread: bool | None = None,
    is_vip: bool | None = None,
    rating_min: int | None = None,
    date_from: str = "",
    date_to: str = "",
    ingestion_method: str = "",
    max_results: int = 20,
) -> str:
    """Search the reading library with optional filters. If query is provided, searches by semantic similarity then applies filters. If query is empty, does a SQL-only filtered search. Filters: author, source (name/domain), tag, ai_tier (must-read/summary-enough/discard), is_unread, is_vip, rating_min (-1/1/2), date_from/date_to (YYYY-MM-DD), ingestion_method (manual/extension/imap/api)."""
    config = _get_config()

    # Semantic search first if query provided
    candidate_ids = None
    score_map = {}
    if query:
        collection = get_collection()
        count = collection.count()
        if count == 0:
            return "No articles in the library yet."

        results = collection.query(
            query_texts=[query],
            n_results=min(max_results * 2, count),
            include=["metadatas", "distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return "No matching articles found."

        candidate_ids = []
        for chroma_id, distance in zip(results["ids"][0], results["distances"][0]):
            article_id = int(chroma_id.replace("article_", ""))
            similarity = round(1 - (distance / 2), 4)
            candidate_ids.append(article_id)
            score_map[article_id] = similarity

    where, params, tag_join = _build_filter_sql(
        author=author, source=source, tag=tag, ai_tier=ai_tier,
        is_unread=is_unread, is_vip=is_vip, rating_min=rating_min,
        date_from=date_from, date_to=date_to, ingestion_method=ingestion_method,
        article_ids=candidate_ids,
    )

    conn = get_connection(config.db_path)
    try:
        sql = f"""SELECT a.id, a.title, a.author, a.summary, a.reading_time_min,
                         a.ingested_at, a.is_read, a.rating, a.url, a.ai_tier,
                         s.name AS source_name, s.is_vip, s.source_type
                  FROM articles a
                  LEFT JOIN sources s ON a.source_id = s.id
                  {tag_join}
                  WHERE {where}
                  ORDER BY s.is_vip DESC, COALESCE(a.published_at, a.ingested_at) DESC
                  LIMIT ?"""
        params.append(max_results)
        rows = conn.execute(sql, params).fetchall()

        if not rows:
            desc = f'matching "{query}"' if query else "matching filters"
            return f"No articles found {desc}."

        # If semantic search, sort by similarity
        if score_map:
            rows = sorted(rows, key=lambda r: score_map.get(r["id"], 0), reverse=True)

        article_ids = [r["id"] for r in rows]
        tags_map = _batch_fetch_tags(conn, article_ids)

        desc = f'matching "{query}"' if query else "matching filters"
        header = f"Found {len(rows)} articles {desc}:\n\n"
        return header + _format_articles(rows, tags_map, score_map if score_map else None)
    finally:
        conn.close()


@mcp.tool()
def list_filters() -> str:
    """List available filter values with counts. Use this to discover what authors, sources, tags, tiers, and ingestion methods exist in the library before searching."""
    config = _get_config()
    conn = get_connection(config.db_path)
    try:
        lines = ["## Available Filters\n"]

        # Tiers
        tier_rows = conn.execute(
            "SELECT ai_tier, COUNT(*) as count FROM articles WHERE ai_tier IS NOT NULL GROUP BY ai_tier ORDER BY count DESC"
        ).fetchall()
        unclassified = conn.execute("SELECT COUNT(*) as count FROM articles WHERE ai_tier IS NULL").fetchone()["count"]
        lines.append("### Tiers")
        for r in tier_rows:
            lines.append(f"- {r['ai_tier']}: {r['count']}")
        lines.append(f"- unclassified: {unclassified}\n")

        # Sources
        source_rows = conn.execute(
            """SELECT s.name, s.domain, COUNT(a.id) as count, s.is_vip, s.source_type
               FROM sources s LEFT JOIN articles a ON s.id = a.source_id
               GROUP BY s.id ORDER BY count DESC"""
        ).fetchall()
        lines.append("### Sources")
        for r in source_rows:
            vip = " [VIP]" if r["is_vip"] else ""
            lines.append(f"- {r['name']} ({r['source_type']}): {r['count']} articles{vip}")
        lines.append("")

        # Tags (top 30)
        tag_rows = conn.execute(
            """SELECT t.name, COUNT(at.article_id) as count
               FROM tags t JOIN article_tags at ON t.id = at.tag_id
               GROUP BY t.name ORDER BY count DESC LIMIT 30"""
        ).fetchall()
        lines.append("### Tags (top 30)")
        for r in tag_rows:
            lines.append(f"- {r['name']}: {r['count']}")
        lines.append("")

        # Ratings
        rating_rows = conn.execute(
            "SELECT rating, COUNT(*) as count FROM articles WHERE rating IS NOT NULL GROUP BY rating ORDER BY rating DESC"
        ).fetchall()
        unrated = conn.execute("SELECT COUNT(*) as count FROM articles WHERE rating IS NULL").fetchone()["count"]
        labels = {-1: "Disliked", 1: "Liked", 2: "Loved"}
        lines.append("### Ratings")
        for r in rating_rows:
            lines.append(f"- {labels.get(r['rating'], r['rating'])}: {r['count']}")
        lines.append(f"- Unrated: {unrated}\n")

        # Ingestion methods
        method_rows = conn.execute(
            "SELECT ingestion_method, COUNT(*) as count FROM articles GROUP BY ingestion_method ORDER BY count DESC"
        ).fetchall()
        lines.append("### Ingestion Methods")
        for r in method_rows:
            lines.append(f"- {r['ingestion_method'] or 'unknown'}: {r['count']}")
        lines.append("")

        # Read status
        read = conn.execute("SELECT COUNT(*) as count FROM articles WHERE is_read = 1").fetchone()["count"]
        unread = conn.execute("SELECT COUNT(*) as count FROM articles WHERE is_read = 0").fetchone()["count"]
        lines.append(f"### Read Status\n- Read: {read}\n- Unread: {unread}\n")

        total = conn.execute("SELECT COUNT(*) as count FROM articles").fetchone()["count"]
        lines.append(f"**Total articles: {total}**")

        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def get_article(article_id: int) -> str:
    """Get the full content and metadata of a specific article by its ID."""
    config = _get_config()
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            """SELECT a.id, a.title, a.author, a.url, a.summary,
                      a.word_count, a.reading_time_min, a.published_at, a.ingested_at,
                      a.is_read, a.rating, a.markdown_path,
                      s.name AS source_name, s.is_vip, s.source_type
               FROM articles a
               LEFT JOIN sources s ON a.source_id = s.id
               WHERE a.id = ?""",
            (article_id,),
        ).fetchone()

        if not row:
            return f"Article with ID {article_id} not found."

        article = dict(row)

        # Fetch tags
        tag_rows = conn.execute(
            """SELECT t.name FROM article_tags at
               JOIN tags t ON at.tag_id = t.id
               WHERE at.article_id = ?""",
            (article_id,),
        ).fetchall()
        tags = [r["name"] for r in tag_rows]

        # Fetch entities
        entity_rows = conn.execute(
            """SELECT e.name, e.entity_type FROM article_entities ae
               JOIN entities e ON ae.entity_id = e.id
               WHERE ae.article_id = ?""",
            (article_id,),
        ).fetchall()
        entities = [f"{r['name']} ({r['entity_type']})" for r in entity_rows]

        # Read markdown content
        md_path = config.articles_dir / article["markdown_path"]
        content = ""
        if md_path.exists():
            post = frontmatter.load(str(md_path))
            content = post.content

        vip = " [VIP Source]" if article["is_vip"] else ""
        rating_label = {-1: "Disliked", 1: "Liked", 2: "Loved"}.get(article["rating"], "Unrated")

        header = (
            f"# {article['title']}\n\n"
            f"**Source:** {article['source_name'] or 'Unknown'}{vip}\n"
            f"**Author:** {article['author'] or 'Unknown'}\n"
            f"**Published:** {article['published_at'] or 'Unknown'}\n"
            f"**Reading time:** {article['reading_time_min'] or '?'} min "
            f"({article['word_count'] or '?'} words)\n"
            f"**Rating:** {rating_label}\n"
            f"**URL:** {article['url'] or 'N/A'}\n"
            f"**Tags:** {', '.join(tags) or 'none'}\n"
            f"**Entities:** {', '.join(entities) or 'none'}\n\n"
            f"## Summary\n{article['summary'] or 'No summary'}\n\n"
            f"## Full Content\n{content}"
        )
        return header
    finally:
        conn.close()


@mcp.tool()
def get_digest(digest_type: str = "ranked") -> str:
    """Get today's daily digest. Types: 'ranked' (by importance), 'by_topic' (grouped by theme), 'by_entity' (grouped by people/companies)."""
    config = _get_config()
    today = date.today().isoformat()

    conn = get_connection(config.db_path)
    try:
        # Try today first, then fall back to most recent
        if digest_type not in ("ranked", "by_topic", "by_entity"):
            return f"Invalid digest type '{digest_type}'. Use: ranked, by_topic, or by_entity."

        row = conn.execute(
            """SELECT content, article_ids, created_at, date FROM digests
               WHERE digest_type = ?
               ORDER BY CASE WHEN date = ? THEN 0 ELSE 1 END, date DESC
               LIMIT 1""",
            (digest_type, today),
        ).fetchone()

        if not row:
            return (
                "No digest found. Generate one first by visiting the Tiro web UI "
                "and clicking the Digest tab, or calling GET /api/digest/today on the running server."
            )

        digest_date = row["date"]
        created = row["created_at"]
        content = row["content"]
        article_ids = json.loads(row["article_ids"])

        header = (
            f"## Daily Digest — {digest_type.replace('_', ' ').title()}\n"
            f"*Generated: {created} | Date: {digest_date} | "
            f"Based on {len(article_ids)} articles*\n\n"
        )
        return header + content
    finally:
        conn.close()


@mcp.tool()
def get_articles_by_tag(tag: str) -> str:
    """Get all articles with a specific tag. Tags are lowercase topic keywords extracted from articles."""
    return search_articles(tag=tag, max_results=50)


@mcp.tool()
def get_articles_by_source(source: str) -> str:
    """Get all articles from a specific source. Matches by source name or domain."""
    return search_articles(source=source, max_results=50)


@mcp.tool()
async def save_url(url: str) -> str:
    """Save a web page to the Tiro reading library by URL. Fetches the page, extracts content, generates tags/summary with AI, and stores it."""
    config = _get_config()

    from tiro.ingestion.web import fetch_and_extract
    from tiro.ingestion.processor import process_article

    try:
        extracted = await fetch_and_extract(url)
    except Exception as e:
        return f"Failed to fetch URL: {e}"

    try:
        result = await asyncio.to_thread(process_article, **extracted, config=config)
    except Exception as e:
        return f"Failed to process article: {e}"

    tags = ", ".join(result.get("tags", []))
    return (
        f"Saved successfully!\n\n"
        f"**{result['title']}** (ID: {result['id']})\n"
        f"Source: {result['source']}\n"
        f"Words: {result['word_count']} | Reading time: {result['reading_time_min']} min\n"
        f"Tags: {tags or 'none'}\n"
        f"Summary: {result.get('summary', 'N/A')}"
    )


@mcp.tool()
def save_email(file_path: str) -> str:
    """Save an email newsletter (.eml file) to the Tiro reading library. Parses the email, extracts content, generates tags/summary with AI, and stores it."""
    config = _get_config()

    from tiro.ingestion.email import parse_eml
    from tiro.ingestion.processor import process_article

    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        return f"File not found: {path}"
    if not path.suffix.lower() == ".eml":
        return f"Expected a .eml file, got: {path.name}"

    try:
        extracted = parse_eml(path)
    except Exception as e:
        return f"Failed to parse email: {e}"

    try:
        result = process_article(**extracted, config=config)
    except Exception as e:
        return f"Failed to process email article: {e}"

    tags = ", ".join(result.get("tags", []))
    return (
        f"Saved successfully!\n\n"
        f"**{result['title']}** (ID: {result['id']})\n"
        f"Source: {result['source']}\n"
        f"Words: {result['word_count']} | Reading time: {result['reading_time_min']} min\n"
        f"Tags: {tags or 'none'}\n"
        f"Summary: {result.get('summary', 'N/A')}"
    )


def main():
    """Entry point for the MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    global _config
    _config = load_config()
    init_vectorstore(_config.chroma_dir, _config.default_embedding_model)
    logger.info("Tiro MCP server starting (library: %s)", _config.library)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
