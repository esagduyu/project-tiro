"""Semantic search over the article library via ChromaDB."""

import logging

from tiro.config import TiroConfig
from tiro.database import get_connection
from tiro.vectorstore import get_collection

logger = logging.getLogger(__name__)


def search_articles(query: str, config: TiroConfig, limit: int = 10) -> list[dict]:
    """Search articles by semantic similarity using ChromaDB.

    Returns a list of dicts with: id, title, source_name, domain, is_vip,
    summary, reading_time_min, ingested_at, similarity_score, tags.
    """
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(limit, count),
        include=["metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    # ChromaDB cosine distance: 0 = identical, 2 = opposite
    # Convert to similarity: 1 - (distance / 2) → range [0, 1]
    ids_and_scores = []
    for chroma_id, distance in zip(results["ids"][0], results["distances"][0]):
        article_id = int(chroma_id.replace("article_", ""))
        similarity = round(1 - (distance / 2), 4)
        ids_and_scores.append((article_id, similarity))

    if not ids_and_scores:
        return []

    article_ids = [aid for aid, _ in ids_and_scores]
    score_map = {aid: score for aid, score in ids_and_scores}

    conn = get_connection(config.db_path)
    try:
        placeholders = ",".join("?" * len(article_ids))
        rows = conn.execute(
            f"""SELECT a.id, a.title, a.summary, a.reading_time_min, a.ingested_at,
                       a.is_read, a.rating,
                       s.name AS source_name, s.domain, s.is_vip, s.id AS source_id,
                       s.source_type
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

        # Build results in similarity order
        results_list = []
        for aid, score in ids_and_scores:
            if aid not in row_map:
                continue
            r = row_map[aid]
            r["similarity_score"] = score
            r["tags"] = tags_map.get(aid, [])
            results_list.append(r)

        return results_list
    finally:
        conn.close()


def find_related_articles(
    article_id: int,
    config: TiroConfig,
    limit: int = 5,
) -> list[dict]:
    """Find the most similar articles to the given article using ChromaDB.

    Returns list of dicts with: related_article_id, similarity_score.
    """
    collection = get_collection()
    chroma_id = f"article_{article_id}"

    try:
        existing = collection.get(ids=[chroma_id], include=["documents"])
    except Exception:
        logger.warning("Article %d not found in ChromaDB", article_id)
        return []

    if not existing["documents"] or not existing["documents"][0]:
        return []

    doc_text = existing["documents"][0]

    count = collection.count()
    if count <= 1:
        return []

    results = collection.query(
        query_texts=[doc_text],
        n_results=min(limit + 1, count),
        include=["metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    related = []
    for cid, distance in zip(results["ids"][0], results["distances"][0]):
        rid = int(cid.replace("article_", ""))
        if rid == article_id:
            continue
        similarity = round(1 - (distance / 2), 4)
        related.append({"related_article_id": rid, "similarity_score": similarity})

    return related[:limit]


def store_relations(
    article_id: int,
    relations: list[dict],
    config: TiroConfig,
) -> None:
    """Store article relations in SQLite. Overwrites existing relations for this article."""
    conn = get_connection(config.db_path)
    try:
        conn.execute("DELETE FROM article_relations WHERE article_id = ?", (article_id,))
        for rel in relations:
            conn.execute(
                """INSERT OR REPLACE INTO article_relations
                   (article_id, related_article_id, similarity_score, connection_note)
                   VALUES (?, ?, ?, ?)""",
                (
                    article_id,
                    rel["related_article_id"],
                    rel["similarity_score"],
                    rel.get("connection_note"),
                ),
            )
        conn.commit()
        logger.info("Stored %d relations for article %d", len(relations), article_id)
    finally:
        conn.close()


def get_related_articles(article_id: int, config: TiroConfig) -> list[dict]:
    """Get stored related articles with full metadata from SQLite."""
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute(
            """SELECT ar.related_article_id, ar.similarity_score, ar.connection_note,
                      a.title, a.summary, a.reading_time_min, a.ingested_at,
                      s.name AS source_name, s.domain, s.is_vip
               FROM article_relations ar
               JOIN articles a ON ar.related_article_id = a.id
               LEFT JOIN sources s ON a.source_id = s.id
               WHERE ar.article_id = ?
               ORDER BY ar.similarity_score DESC""",
            (article_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def generate_connection_notes(
    article_summary: str,
    article_title: str,
    related_articles: list[dict],
    config: TiroConfig,
) -> list[dict]:
    """Use Haiku to generate brief connection notes for the top related articles.

    Updates the related_articles list in-place with connection_note field.
    Only processes top 3 to save API costs.
    """
    import json
    import os

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return related_articles

    if not related_articles:
        return related_articles

    to_annotate = related_articles[:3]

    conn = get_connection(config.db_path)
    try:
        ids = [r["related_article_id"] for r in to_annotate]
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT id, title, summary FROM articles WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        summary_map = {r["id"]: {"title": r["title"], "summary": r["summary"] or ""} for r in rows}
    finally:
        conn.close()

    related_context = "\n".join(
        f"- Article {r['related_article_id']}: \"{summary_map.get(r['related_article_id'], {}).get('title', '?')}\" — {summary_map.get(r['related_article_id'], {}).get('summary', 'No summary')}"
        for r in to_annotate
    )

    prompt = (
        "You are a reading assistant. Given a source article and related articles, "
        "write a brief connection note (1 sentence, max 20 words) for each related article "
        "explaining HOW it relates to the source. Use phrases like "
        '"Contradicts...", "Builds on...", "Different perspective on...", '
        '"Earlier coverage of...", "Same topic from...".\n\n'
        f'Source article: "{article_title}"\n'
        f"Summary: {article_summary}\n\n"
        f"Related articles:\n{related_context}\n\n"
        "Respond with JSON only:\n"
        '{"notes": [{"article_id": 123, "note": "connection note"}, ...]}'
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=config.haiku_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)
        note_map = {n["article_id"]: n["note"] for n in data.get("notes", [])}

        for r in related_articles:
            if r["related_article_id"] in note_map:
                r["connection_note"] = note_map[r["related_article_id"]]

    except Exception as e:
        logger.error("Connection note generation failed: %s", e)

    return related_articles
