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


@mcp.tool()
def search_articles(query: str) -> str:
    """Search the reading library by semantic similarity. Returns the most relevant articles matching the query."""
    config = _get_config()
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return "No articles in the library yet."

    results = collection.query(
        query_texts=[query],
        n_results=min(10, count),
        include=["metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return "No matching articles found."

    # Get article IDs and similarity scores
    ids_and_scores = []
    for chroma_id, distance in zip(results["ids"][0], results["distances"][0]):
        article_id = int(chroma_id.replace("article_", ""))
        similarity = round(1 - (distance / 2), 4)
        ids_and_scores.append((article_id, similarity))

    article_ids = [aid for aid, _ in ids_and_scores]
    score_map = {aid: score for aid, score in ids_and_scores}

    conn = get_connection(config.db_path)
    try:
        placeholders = ",".join("?" * len(article_ids))
        rows = conn.execute(
            f"""SELECT a.id, a.title, a.author, a.summary, a.reading_time_min,
                       a.ingested_at, a.is_read, a.rating, a.url,
                       s.name AS source_name, s.is_vip, s.source_type
                FROM articles a
                LEFT JOIN sources s ON a.source_id = s.id
                WHERE a.id IN ({placeholders})""",
            article_ids,
        ).fetchall()

        row_map = {r["id"]: dict(r) for r in rows}

        # Batch-fetch tags
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

        lines = [f"Found {len(ids_and_scores)} articles matching \"{query}\":\n"]
        for aid, score in ids_and_scores:
            if aid not in row_map:
                continue
            r = row_map[aid]
            vip = " [VIP]" if r["is_vip"] else ""
            tags = ", ".join(tags_map.get(aid, []))
            lines.append(
                f"- **{r['title']}** (ID: {aid}, similarity: {score:.0%}){vip}\n"
                f"  Source: {r['source_name'] or 'Unknown'} | "
                f"{r['reading_time_min'] or '?'} min read | "
                f"Tags: {tags or 'none'}\n"
                f"  Summary: {r['summary'] or 'No summary'}\n"
            )
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
    config = _get_config()
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute(
            """SELECT a.id, a.title, a.author, a.summary, a.reading_time_min,
                      a.ingested_at, a.is_read, a.rating, a.url,
                      s.name AS source_name, s.is_vip, s.source_type
               FROM articles a
               LEFT JOIN sources s ON a.source_id = s.id
               JOIN article_tags at ON a.id = at.article_id
               JOIN tags t ON at.tag_id = t.id
               WHERE t.name = ?
               ORDER BY s.is_vip DESC, a.ingested_at DESC""",
            (tag.lower().strip(),),
        ).fetchall()

        if not rows:
            # Show available tags to help the user
            all_tags = conn.execute(
                """SELECT t.name, COUNT(at.article_id) as count
                   FROM tags t JOIN article_tags at ON t.id = at.tag_id
                   GROUP BY t.name ORDER BY count DESC LIMIT 20"""
            ).fetchall()
            tag_list = ", ".join(f"{r['name']} ({r['count']})" for r in all_tags)
            return f"No articles found with tag \"{tag}\".\n\nAvailable tags: {tag_list or 'none'}"

        # Batch-fetch tags for all found articles
        article_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(article_ids))
        tag_rows = conn.execute(
            f"""SELECT at.article_id, t.name
                FROM article_tags at JOIN tags t ON at.tag_id = t.id
                WHERE at.article_id IN ({placeholders})""",
            article_ids,
        ).fetchall()
        tags_map: dict[int, list[str]] = {}
        for tr in tag_rows:
            tags_map.setdefault(tr["article_id"], []).append(tr["name"])

        lines = [f"Found {len(rows)} articles tagged \"{tag}\":\n"]
        for r in rows:
            r = dict(r)
            vip = " [VIP]" if r["is_vip"] else ""
            all_tags = ", ".join(tags_map.get(r["id"], []))
            rating_label = {-1: "👎", 1: "👍", 2: "❤️"}.get(r["rating"], "")
            lines.append(
                f"- **{r['title']}** (ID: {r['id']}){vip} {rating_label}\n"
                f"  Source: {r['source_name'] or 'Unknown'} | "
                f"{r['reading_time_min'] or '?'} min read | "
                f"Tags: {all_tags}\n"
                f"  Summary: {r['summary'] or 'No summary'}\n"
            )
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def get_articles_by_source(source: str) -> str:
    """Get all articles from a specific source. Matches by source name or domain."""
    config = _get_config()
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute(
            """SELECT a.id, a.title, a.author, a.summary, a.reading_time_min,
                      a.ingested_at, a.is_read, a.rating, a.url,
                      s.name AS source_name, s.domain, s.is_vip, s.source_type
               FROM articles a
               LEFT JOIN sources s ON a.source_id = s.id
               WHERE s.name LIKE ? OR s.domain LIKE ?
               ORDER BY a.ingested_at DESC""",
            (f"%{source}%", f"%{source}%"),
        ).fetchall()

        if not rows:
            # Show available sources
            all_sources = conn.execute(
                """SELECT s.name, s.domain, COUNT(a.id) as count, s.is_vip
                   FROM sources s LEFT JOIN articles a ON s.id = a.source_id
                   GROUP BY s.id ORDER BY count DESC"""
            ).fetchall()
            source_list = "\n".join(
                f"  - {r['name']} ({r['domain'] or 'email'}) — {r['count']} articles"
                + (" [VIP]" if r["is_vip"] else "")
                for r in all_sources
            )
            return f"No articles found from source \"{source}\".\n\nAvailable sources:\n{source_list or 'none'}"

        # Batch-fetch tags
        article_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(article_ids))
        tag_rows = conn.execute(
            f"""SELECT at.article_id, t.name
                FROM article_tags at JOIN tags t ON at.tag_id = t.id
                WHERE at.article_id IN ({placeholders})""",
            article_ids,
        ).fetchall()
        tags_map: dict[int, list[str]] = {}
        for tr in tag_rows:
            tags_map.setdefault(tr["article_id"], []).append(tr["name"])

        source_name = rows[0]["source_name"]
        vip = " [VIP]" if rows[0]["is_vip"] else ""
        lines = [f"Found {len(rows)} articles from \"{source_name}\"{vip}:\n"]
        for r in rows:
            r = dict(r)
            tags = ", ".join(tags_map.get(r["id"], []))
            rating_label = {-1: "👎", 1: "👍", 2: "❤️"}.get(r["rating"], "")
            lines.append(
                f"- **{r['title']}** (ID: {r['id']}) {rating_label}\n"
                f"  {r['reading_time_min'] or '?'} min read | "
                f"Tags: {tags or 'none'}\n"
                f"  Summary: {r['summary'] or 'No summary'}\n"
            )
        return "\n".join(lines)
    finally:
        conn.close()


@mcp.tool()
def save_url(url: str) -> str:
    """Save a web page to the Tiro reading library by URL. Fetches the page, extracts content, generates tags/summary with AI, and stores it."""
    config = _get_config()

    from tiro.ingestion.web import fetch_and_extract
    from tiro.ingestion.processor import process_article

    try:
        extracted = asyncio.run(fetch_and_extract(url))
    except Exception as e:
        return f"Failed to fetch URL: {e}"

    try:
        result = process_article(**extracted, config=config)
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
