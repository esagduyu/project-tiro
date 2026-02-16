"""Knowledge graph API routes."""

import logging
from collections import defaultdict

from fastapi import APIRouter, Request

from tiro.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
async def get_graph(request: Request, min_articles: int = 2):
    """Return nodes and edges for the knowledge graph visualization.

    Nodes: entities and tags appearing in at least `min_articles` articles.
    Edges: co-occurrence in articles, weighted by shared article count.
    """
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        # Fetch all article-entity associations
        ae_rows = conn.execute(
            "SELECT article_id, entity_id FROM article_entities"
        ).fetchall()

        # Fetch all article-tag associations
        at_rows = conn.execute(
            "SELECT article_id, tag_id FROM article_tags"
        ).fetchall()

        # Fetch entity metadata
        entity_rows = conn.execute(
            "SELECT id, name, entity_type FROM entities"
        ).fetchall()
        entities = {r["id"]: dict(r) for r in entity_rows}

        # Fetch tag metadata
        tag_rows = conn.execute(
            "SELECT id, name FROM tags"
        ).fetchall()
        tags = {r["id"]: dict(r) for r in tag_rows}

        # Build article_id -> set of node_ids mapping
        article_nodes = defaultdict(set)
        node_article_count = defaultdict(int)

        for row in ae_rows:
            node_id = f"entity:{row['entity_id']}"
            article_nodes[row["article_id"]].add(node_id)

        for row in at_rows:
            node_id = f"tag:{row['tag_id']}"
            article_nodes[row["article_id"]].add(node_id)

        # Count articles per node
        for nodes in article_nodes.values():
            for node_id in nodes:
                node_article_count[node_id] += 1

        # Filter nodes by min_articles threshold
        valid_nodes = {
            nid for nid, count in node_article_count.items()
            if count >= min_articles
        }

        # Build node list
        nodes = []
        for nid in valid_nodes:
            kind, raw_id = nid.split(":", 1)
            raw_id = int(raw_id)
            if kind == "entity" and raw_id in entities:
                e = entities[raw_id]
                nodes.append({
                    "id": nid,
                    "label": e["name"],
                    "type": e["entity_type"],
                    "count": node_article_count[nid],
                })
            elif kind == "tag" and raw_id in tags:
                t = tags[raw_id]
                nodes.append({
                    "id": nid,
                    "label": t["name"],
                    "type": "tag",
                    "count": node_article_count[nid],
                })

        # Build edges: count co-occurrences between valid node pairs
        edge_counts = defaultdict(int)
        for article_id, node_set in article_nodes.items():
            # Only consider nodes that pass the filter
            filtered = sorted(node_set & valid_nodes)
            for i in range(len(filtered)):
                for j in range(i + 1, len(filtered)):
                    pair = (filtered[i], filtered[j])
                    edge_counts[pair] += 1

        edges = [
            {"source": src, "target": tgt, "weight": weight}
            for (src, tgt), weight in edge_counts.items()
        ]

        return {
            "success": True,
            "data": {"nodes": nodes, "edges": edges},
        }
    finally:
        conn.close()


@router.get("/node/{node_type}/{node_id}/articles")
async def get_node_articles(node_type: str, node_id: int, request: Request):
    """Return articles linked to a specific entity or tag node."""
    config = request.app.state.config
    conn = get_connection(config.db_path)
    try:
        if node_type == "entity":
            rows = conn.execute("""
                SELECT a.id, a.title, s.name AS source_name, a.ingested_at
                FROM articles a
                JOIN article_entities ae ON a.id = ae.article_id
                LEFT JOIN sources s ON a.source_id = s.id
                WHERE ae.entity_id = ?
                ORDER BY COALESCE(a.published_at, a.ingested_at) DESC
            """, (node_id,)).fetchall()
        elif node_type == "tag":
            rows = conn.execute("""
                SELECT a.id, a.title, s.name AS source_name, a.ingested_at
                FROM articles a
                JOIN article_tags at_ ON a.id = at_.article_id
                LEFT JOIN sources s ON a.source_id = s.id
                WHERE at_.tag_id = ?
                ORDER BY COALESCE(a.published_at, a.ingested_at) DESC
            """, (node_id,)).fetchall()
        else:
            return {
                "success": False,
                "error": f"Invalid node_type '{node_type}'. Must be 'entity' or 'tag'.",
            }

        return {"success": True, "data": [dict(r) for r in rows]}
    finally:
        conn.close()
