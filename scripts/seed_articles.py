"""Seed the Tiro library with demo articles.

Ingests web articles, sets ratings/VIP/read state to match a realistic demo.
Requires ANTHROPIC_API_KEY (for Haiku tag/entity/summary extraction).

Run from project root:
    uv run python scripts/seed_articles.py
"""

import asyncio
import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tiro.config import load_config
from tiro.database import init_db
from tiro.ingestion.processor import process_article
from tiro.ingestion.web import fetch_and_extract
from tiro.vectorstore import init_vectorstore

# --- Article URLs to seed ---
# Each tuple: (url, rating, is_read)
#   rating: None = unrated, -1 = dislike, 1 = like, 2 = love
ARTICLES = [
    # Paul Graham essays
    ("https://paulgraham.com/greatwork.html", None, True),
    ("https://paulgraham.com/read.html", 1, True),
    ("https://www.paulgraham.com/think.html", None, True),
    ("https://www.paulgraham.com/superlinear.html", None, True),
    ("https://www.paulgraham.com/startupideas.html", None, True),
    ("https://paulgraham.com/writes.html", None, True),
    ("https://paulgraham.com/ds.html", None, True),
    ("https://paulgraham.com/hwh.html", 2, True),
    ("https://paulgraham.com/users.html", None, True),
    # Stratechery
    ("https://stratechery.com/2026/microsoft-and-software-survival/", 2, True),
    ("https://stratechery.com/2026/tsmc-risk/", 2, True),
    ("https://stratechery.com/2025/deepseek-faq/", 2, True),
    # Dario Amodei
    ("https://darioamodei.com/on-deepseek-and-export-controls", None, True),
    ("https://darioamodei.com/machines-of-loving-grace", 2, True),
    # Zvi / AI
    ("https://thezvi.substack.com/p/claude-opus-46-system-card-part-2", None, True),
    ("https://thezvi.substack.com/p/chatgpt-53-codex-is-also-good-at", None, True),
    # SemiAnalysis
    ("https://newsletter.semianalysis.com/p/claude-code-is-the-inflection-point", None, True),
    # Derek Thompson
    ("https://www.derekthompson.org/p/why-americas-ai-discourse-feels-so", None, True),
    # News / misc (for diversity — some will be disliked/discarded)
    ("https://www.cbc.ca/sports/olympics/winter/curling/olympic-mens-curling-controversy-canada-9.7091098", None, True),
    ("https://www.foxnews.com/media/homan-tells-minnesota-leaders-say-thank-you-instead-demanding-reimbursement-ice-operation-ends", None, True),
    ("https://www.wired.com/story/i-tried-rentahuman-ai-agents-hired-me-to-hype-their-ai-startups/", None, True),
    ("https://steipete.me/posts/2026/openclaw", None, True),
]

# VIP sources (by domain substring)
VIP_SOURCES = ["stratechery.com"]

# Ratings to apply after ingestion (by title substring -> rating)
# Only for articles with explicit ratings in the demo library
POST_RATINGS = {
    "How to Do Great Work": -1,
}


async def main():
    config = load_config()
    config.articles_dir.mkdir(parents=True, exist_ok=True)
    init_db(config.db_path)
    init_vectorstore(config.chroma_dir, config.default_embedding_model)

    success = 0
    failed = 0
    ingested_ids = []

    total = len(ARTICLES)
    for i, (url, rating, is_read) in enumerate(ARTICLES, 1):
        print(f"\n[{i}/{total}] Ingesting: {url}")
        try:
            extracted = await fetch_and_extract(url)
            if not extracted:
                print("  SKIP: extraction returned None")
                failed += 1
                continue

            result = process_article(**extracted, config=config)
            article_id = result["id"]
            title = result.get("title", "?")
            words = result.get("word_count", "?")
            print(f"  OK: {title} ({words} words)")
            ingested_ids.append((article_id, rating, is_read))
            success += 1
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                print(f"  SKIP: already in library")
            else:
                print(f"  FAIL: {e}")
            failed += 1

    # --- Post-processing: set ratings, read status, VIP ---
    conn = sqlite3.connect(str(config.db_path))
    cursor = conn.cursor()

    # Set ratings and read status
    for article_id, rating, is_read in ingested_ids:
        if rating is not None:
            cursor.execute("UPDATE articles SET rating = ? WHERE id = ?", (rating, article_id))
        if is_read:
            cursor.execute("UPDATE articles SET is_read = 1, opened_count = 1 WHERE id = ?", (article_id,))

    # Apply title-based ratings
    for title_substr, rating in POST_RATINGS.items():
        cursor.execute(
            "UPDATE articles SET rating = ? WHERE title LIKE ?",
            (rating, f"%{title_substr}%"),
        )

    # Set VIP sources
    for domain in VIP_SOURCES:
        cursor.execute(
            "UPDATE sources SET is_vip = 1 WHERE domain LIKE ?",
            (f"%{domain}%",),
        )

    conn.commit()

    # Summary
    total_articles = cursor.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_sources = cursor.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    vip_count = cursor.execute("SELECT COUNT(*) FROM sources WHERE is_vip = 1").fetchone()[0]
    rated_count = cursor.execute("SELECT COUNT(*) FROM articles WHERE rating IS NOT NULL").fetchone()[0]
    conn.close()

    print(f"\n{'='*50}")
    print(f"Seed complete!")
    print(f"  Ingested: {success} articles ({failed} failed/skipped)")
    print(f"  Library:  {total_articles} articles, {total_sources} sources")
    print(f"  Rated:    {rated_count} articles")
    print(f"  VIP:      {vip_count} sources")
    print(f"\nNext steps:")
    print(f"  uv run tiro run          # Start the server")
    print(f"  # Then: rate a few articles and run 'Classify inbox' for the full demo experience")


if __name__ == "__main__":
    asyncio.run(main())
