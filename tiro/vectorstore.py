"""ChromaDB vector store initialization and helpers for Tiro."""

import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def init_vectorstore(chroma_dir: Path) -> chromadb.Collection:
    """Initialize the ChromaDB persistent client and return the tiro_articles collection."""
    global _client, _collection

    chroma_dir.mkdir(parents=True, exist_ok=True)

    _client = chromadb.PersistentClient(path=str(chroma_dir))
    _collection = _client.get_or_create_collection(
        name="tiro_articles",
        metadata={"hnsw:space": "cosine"},
    )
    logger.info(
        "ChromaDB initialized at %s (%d documents)",
        chroma_dir,
        _collection.count(),
    )
    return _collection


def get_collection() -> chromadb.Collection:
    """Get the tiro_articles collection. Must call init_vectorstore first."""
    if _collection is None:
        raise RuntimeError("Vectorstore not initialized. Call init_vectorstore first.")
    return _collection
