"""Seed the Tiro library with demo articles for testing the digest feature.

Run from project root with direnv active (for ANTHROPIC_API_KEY):
    uv run python scripts/seed_articles.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tiro.config import load_config
from tiro.database import init_db
from tiro.vectorstore import init_vectorstore
from tiro.ingestion.web import fetch_and_extract
from tiro.ingestion.processor import process_article

URLS = [
    # Paul Graham essays — cross-reference with existing PG articles
    "https://www.paulgraham.com/think.html",
    "https://www.paulgraham.com/superlinear.html",
    "https://www.paulgraham.com/writes.html",
    "https://www.paulgraham.com/startupideas.html",
    "https://www.paulgraham.com/ds.html",
    # Dario Amodei — cross-reference with existing AI/Anthropic articles
    "https://darioamodei.com/on-deepseek-and-export-controls",
    "https://darioamodei.com/machines-of-loving-grace",
    # Stratechery (may be paywalled — skip on error)
    "https://stratechery.com/2025/deepseek-faq/",
    # Zvi / AI safety — cross-reference with existing Opus system card article
    "https://thezvi.substack.com/p/on-deepseek-r1",
    "https://thezvi.substack.com/p/ai-policy-is-ai-policy",
]


async def main():
    config = load_config()
    config.articles_dir.mkdir(parents=True, exist_ok=True)
    init_db(config.db_path)
    init_vectorstore(config.chroma_dir, config.default_embedding_model)

    success = 0
    failed = 0

    for i, url in enumerate(URLS, 1):
        print(f"\n[{i}/{len(URLS)}] Ingesting: {url}")
        try:
            extracted = await fetch_and_extract(url)
            if not extracted:
                print("  SKIP: extraction returned None")
                failed += 1
                continue

            result = process_article(**extracted, config=config)
            print(f"  OK: {result.get('title', '?')} ({result.get('word_count', '?')} words)")
            success += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            failed += 1

    # Count total articles in library
    import sqlite3
    conn = sqlite3.connect(str(config.db_path))
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()
    print(f"\nDone: {success} ingested, {failed} failed (total library: {total} articles)")


if __name__ == "__main__":
    asyncio.run(main())
