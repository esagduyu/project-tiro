"""Library export — generates a zip bundle of the user's Tiro library."""

import json
import logging
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from tiro.config import TiroConfig
from tiro.database import get_connection

logger = logging.getLogger(__name__)


def export_library(
    config: TiroConfig,
    *,
    tag: str | None = None,
    source_id: int | None = None,
    rating_min: int | None = None,
    date_from: str | None = None,
) -> Path:
    """Export the library as a zip file.

    Returns the path to a temporary zip file (caller is responsible for cleanup).
    """
    conn = get_connection(config.db_path)
    try:
        # Build filtered article query
        article_ids = _get_filtered_article_ids(
            conn, tag=tag, source_id=source_id, rating_min=rating_min, date_from=date_from
        )

        # Gather all data
        articles = _get_articles(conn, article_ids)
        sources = _get_sources(conn)
        tags = _get_tags(conn, article_ids)
        entities = _get_entities(conn, article_ids)
        relations = _get_relations(conn, article_ids)
        article_tags = _get_article_tags(conn, article_ids)
        article_entities = _get_article_entities(conn, article_ids)

    finally:
        conn.close()

    # Build the metadata payload
    metadata = {
        "exported_at": datetime.now().isoformat(),
        "tiro_version": "0.1.0",
        "filters": {
            "tag": tag,
            "source_id": source_id,
            "rating_min": rating_min,
            "date_from": date_from,
        },
        "articles": articles,
        "sources": sources,
        "tags": tags,
        "entities": entities,
        "relations": relations,
        "article_tags": article_tags,
        "article_entities": article_entities,
    }

    # Create the zip
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="tiro-export-")
    tmp.close()
    zip_path = Path(tmp.name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add markdown files
        for article in articles:
            md_path = config.articles_dir / article["markdown_path"]
            if md_path.exists():
                arcname = f"articles/{md_path.name}"
                zf.write(md_path, arcname)

        # Add metadata.json
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, default=str))

        # Add README.md
        zf.writestr("README.md", _bundle_readme(len(articles)))

    logger.info("Exported %d articles to %s", len(articles), zip_path)
    return zip_path


def _get_filtered_article_ids(
    conn,
    *,
    tag: str | None = None,
    source_id: int | None = None,
    rating_min: int | None = None,
    date_from: str | None = None,
) -> list[int]:
    """Return article IDs matching the given filters."""
    query = "SELECT DISTINCT a.id FROM articles a"
    joins = []
    conditions = []
    params: list = []

    if tag:
        joins.append("JOIN article_tags at_ ON a.id = at_.article_id")
        joins.append("JOIN tags t ON at_.tag_id = t.id")
        conditions.append("LOWER(t.name) = LOWER(?)")
        params.append(tag)

    if source_id is not None:
        conditions.append("a.source_id = ?")
        params.append(source_id)

    if rating_min is not None:
        conditions.append("a.rating >= ?")
        params.append(rating_min)

    if date_from:
        conditions.append("a.ingested_at >= ?")
        params.append(date_from)

    if joins:
        query += " " + " ".join(joins)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    rows = conn.execute(query, params).fetchall()
    return [row["id"] for row in rows]


def _get_articles(conn, article_ids: list[int]) -> list[dict]:
    """Fetch full article records for the given IDs."""
    if not article_ids:
        return []

    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"""
        SELECT a.*, s.name as source_name, s.source_type, s.is_vip as source_is_vip
        FROM articles a
        LEFT JOIN sources s ON a.source_id = s.id
        WHERE a.id IN ({placeholders})
        ORDER BY a.ingested_at DESC
        """,
        article_ids,
    ).fetchall()

    return [dict(row) for row in rows]


def _get_sources(conn) -> list[dict]:
    """Fetch all sources."""
    rows = conn.execute("SELECT * FROM sources ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def _get_tags(conn, article_ids: list[int]) -> list[dict]:
    """Fetch tags referenced by the filtered articles."""
    if not article_ids:
        return []

    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT t.* FROM tags t
        JOIN article_tags at_ ON t.id = at_.tag_id
        WHERE at_.article_id IN ({placeholders})
        ORDER BY t.name
        """,
        article_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _get_entities(conn, article_ids: list[int]) -> list[dict]:
    """Fetch entities referenced by the filtered articles."""
    if not article_ids:
        return []

    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT e.* FROM entities e
        JOIN article_entities ae ON e.id = ae.entity_id
        WHERE ae.article_id IN ({placeholders})
        ORDER BY e.name
        """,
        article_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _get_relations(conn, article_ids: list[int]) -> list[dict]:
    """Fetch article relations where both sides are in the filtered set."""
    if not article_ids:
        return []

    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"""
        SELECT * FROM article_relations
        WHERE article_id IN ({placeholders})
          AND related_article_id IN ({placeholders})
        """,
        article_ids + article_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _get_article_tags(conn, article_ids: list[int]) -> list[dict]:
    """Fetch article-tag junction rows for the filtered articles."""
    if not article_ids:
        return []

    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"SELECT * FROM article_tags WHERE article_id IN ({placeholders})",
        article_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _get_article_entities(conn, article_ids: list[int]) -> list[dict]:
    """Fetch article-entity junction rows for the filtered articles."""
    if not article_ids:
        return []

    placeholders = ",".join("?" * len(article_ids))
    rows = conn.execute(
        f"SELECT * FROM article_entities WHERE article_id IN ({placeholders})",
        article_ids,
    ).fetchall()
    return [dict(row) for row in rows]


def _bundle_readme(article_count: int) -> str:
    """Generate a README.md for the export bundle."""
    return f"""# Tiro Library Export

This bundle was exported from [Tiro](https://github.com/egebeyaztas/project-tiro), a local-first reading OS.

## Contents

- **articles/**: {article_count} markdown files with YAML frontmatter (title, author, tags, entities, summary, etc.)
- **metadata.json**: Full structured data including articles, sources, tags, entities, ratings, and article relations
- **README.md**: This file

## Markdown File Format

Each article is a markdown file with YAML frontmatter:

```yaml
---
title: "Article Title"
author: "Author Name"
source: "source.com"
url: "https://..."
published: 2026-02-10
ingested: 2026-02-11T14:30:00
tags: ["ai", "technology"]
entities: ["Company A", "Person B"]
word_count: 2450
reading_time: 10 min
---

# Article Title

[Full article content in clean markdown...]
```

## metadata.json Schema

```json
{{
  "exported_at": "ISO 8601 timestamp",
  "tiro_version": "0.1.0",
  "filters": {{ "tag": null, "source_id": null, "rating_min": null, "date_from": null }},
  "articles": [ {{ "id": 1, "title": "...", "rating": 1, "ai_tier": "must-read", ... }} ],
  "sources": [ {{ "id": 1, "name": "...", "domain": "...", "is_vip": true, ... }} ],
  "tags": [ {{ "id": 1, "name": "ai" }} ],
  "entities": [ {{ "id": 1, "name": "Anthropic", "entity_type": "company" }} ],
  "relations": [ {{ "article_id": 1, "related_article_id": 2, "similarity_score": 0.85, "connection_note": "..." }} ],
  "article_tags": [ {{ "article_id": 1, "tag_id": 1 }} ],
  "article_entities": [ {{ "article_id": 1, "entity_id": 1 }} ]
}}
```

## Re-importing

These files are standard markdown with YAML frontmatter, readable by any tool that supports frontmatter (Obsidian, Hugo, Jekyll, python-frontmatter, etc.).

The metadata.json contains the full relational data if you need to reconstruct the database.

---

*Exported by Tiro — own your context.*
"""
