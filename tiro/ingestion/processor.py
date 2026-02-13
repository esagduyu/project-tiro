"""Common processing pipeline for all ingestion connectors."""

import logging
import math
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import frontmatter

from tiro.config import TiroConfig
from tiro.database import get_connection
from tiro.ingestion.extractors import extract_metadata
from tiro.search.semantic import find_related_articles, generate_connection_notes, store_relations
from tiro.vectorstore import get_collection

logger = logging.getLogger(__name__)


def generate_slug(title: str, dt: datetime) -> str:
    """Generate a filename-safe slug from title and date."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = slug[:80].rstrip("-")
    return f"{dt.strftime('%Y-%m-%d')}_{slug}"


def _ensure_unique_slug(slug: str, articles_dir: Path) -> str:
    """Append a numeric suffix if a file with this slug already exists."""
    if not (articles_dir / f"{slug}.md").exists():
        return slug
    n = 2
    while (articles_dir / f"{slug}-{n}.md").exists():
        n += 1
    return f"{slug}-{n}"


def _get_or_create_source(conn, domain: str) -> int:
    """Find existing source by domain or create a new one. Returns source_id."""
    row = conn.execute(
        "SELECT id FROM sources WHERE domain = ?", (domain,)
    ).fetchone()
    if row:
        return row["id"]

    source_name = domain.removeprefix("www.")
    cursor = conn.execute(
        "INSERT INTO sources (name, domain, source_type) VALUES (?, ?, ?)",
        (source_name, domain, "web"),
    )
    conn.commit()
    return cursor.lastrowid


def process_article(
    *,
    title: str,
    author: str | None,
    content_md: str,
    url: str,
    config: TiroConfig,
) -> dict:
    """Run the full storage pipeline: save markdown, insert SQLite, embed in ChromaDB.

    Returns a dict of the created article metadata.
    """
    now = datetime.now()

    # --- Word count & reading time ---
    word_count = len(content_md.split())
    reading_time_min = max(1, math.ceil(word_count / 250))

    # --- Slug & file path ---
    slug = generate_slug(title, now)
    slug = _ensure_unique_slug(slug, config.articles_dir)
    md_filename = f"{slug}.md"
    md_path = config.articles_dir / md_filename

    # --- Source detection ---
    parsed = urlparse(url)
    domain = parsed.netloc
    source_name = domain.removeprefix("www.")

    conn = get_connection(config.db_path)
    try:
        source_id = _get_or_create_source(conn, domain)

        # Check VIP status for ChromaDB metadata
        source_row = conn.execute(
            "SELECT is_vip FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        is_vip = bool(source_row["is_vip"]) if source_row else False

        # --- Save markdown file with YAML frontmatter ---
        post = frontmatter.Post(content_md)
        post.metadata = {
            "title": title,
            "author": author,
            "source": source_name,
            "url": url,
            "published": now.strftime("%Y-%m-%d"),
            "ingested": now.isoformat(timespec="seconds"),
            "tags": [],
            "entities": [],
            "word_count": word_count,
            "reading_time": f"{reading_time_min} min",
        }
        md_path.write_text(frontmatter.dumps(post))
        logger.info("Saved markdown to %s", md_path)

        # --- Insert into SQLite ---
        cursor = conn.execute(
            """INSERT INTO articles
               (source_id, title, author, url, slug, markdown_path,
                word_count, reading_time_min, ingested_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                title,
                author,
                url,
                slug,
                md_filename,
                word_count,
                reading_time_min,
                now.isoformat(),
            ),
        )
        article_id = cursor.lastrowid
        conn.commit()
        logger.info("Inserted article %d into SQLite", article_id)

        # --- AI metadata extraction (Haiku) ---
        ai = extract_metadata(title, content_md, config)
        summary = ai["summary"]
        tag_names = ai["tags"]
        entity_list = ai["entities"]

        if summary:
            conn.execute(
                "UPDATE articles SET summary = ? WHERE id = ?",
                (summary, article_id),
            )

        for tag_name in tag_names:
            conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
            tag_row = conn.execute(
                "SELECT id FROM tags WHERE name = ?", (tag_name,)
            ).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO article_tags (article_id, tag_id) VALUES (?, ?)",
                (article_id, tag_row["id"]),
            )

        for entity in entity_list:
            conn.execute(
                "INSERT OR IGNORE INTO entities (name, entity_type) VALUES (?, ?)",
                (entity["name"], entity["type"]),
            )
            ent_row = conn.execute(
                "SELECT id FROM entities WHERE name = ? AND entity_type = ?",
                (entity["name"], entity["type"]),
            ).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO article_entities (article_id, entity_id) VALUES (?, ?)",
                (article_id, ent_row["id"]),
            )

        conn.commit()

        # Update frontmatter with AI-extracted metadata
        post.metadata["tags"] = tag_names
        post.metadata["entities"] = [e["name"] for e in entity_list]
        if summary:
            post.metadata["summary"] = summary
        md_path.write_text(frontmatter.dumps(post))

        # --- Store in ChromaDB ---
        collection = get_collection()
        collection.add(
            ids=[f"article_{article_id}"],
            documents=[content_md],
            metadatas=[
                {
                    "title": title,
                    "source": source_name,
                    "is_vip": is_vip,
                    "tags": ",".join(tag_names),
                    "published_at": now.strftime("%Y-%m-%d"),
                    "article_id": article_id,
                }
            ],
        )
        logger.info("Added article %d to ChromaDB", article_id)

        # --- Find and store related articles ---
        try:
            relations = find_related_articles(article_id, config, limit=5)
            if relations:
                generate_connection_notes(summary or "", title, relations, config)
                store_relations(article_id, relations, config)
        except Exception as e:
            logger.error("Related articles failed for %d: %s", article_id, e)

        return {
            "id": article_id,
            "title": title,
            "author": author,
            "url": url,
            "slug": slug,
            "source": source_name,
            "word_count": word_count,
            "reading_time_min": reading_time_min,
            "markdown_path": md_filename,
            "summary": summary,
            "tags": tag_names,
        }
    finally:
        conn.close()
