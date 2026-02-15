"""Content decay system for Tiro.

Recalculates relevance_weight for all articles based on engagement signals.
- Liked/Loved articles: immune (weight stays at 1.0)
- No engagement after 7 days: decays by decay_rate_default per day
- Disliked articles: decays faster (decay_rate_disliked per day)
- VIP source articles: decays slower (decay_rate_vip per day)
"""

import logging
from datetime import datetime, timezone

from tiro.config import TiroConfig
from tiro.database import get_connection

logger = logging.getLogger(__name__)

GRACE_PERIOD_DAYS = 7  # no decay for the first 7 days
MIN_WEIGHT = 0.01  # never fully zero


def recalculate_decay(config: TiroConfig) -> dict:
    """Recalculate relevance_weight for all articles.

    Returns summary dict with counts.
    """
    conn = get_connection(config.db_path)
    try:
        rows = conn.execute("""
            SELECT
                a.id, a.rating, a.ingested_at, a.is_read, a.opened_count,
                s.is_vip
            FROM articles a
            LEFT JOIN sources s ON a.source_id = s.id
        """).fetchall()

        now = datetime.now(timezone.utc)
        updated = 0
        immune = 0
        decayed = 0

        for row in rows:
            rating = row["rating"]

            # Liked (1) or Loved (2) articles are immune to decay
            if rating is not None and rating > 0:
                conn.execute(
                    "UPDATE articles SET relevance_weight = 1.0 WHERE id = ?",
                    (row["id"],),
                )
                immune += 1
                continue

            # Calculate days since ingestion
            ingested_str = row["ingested_at"]
            if not ingested_str:
                continue

            try:
                ingested = datetime.fromisoformat(ingested_str.replace(" ", "T"))
                if ingested.tzinfo is None:
                    ingested = ingested.replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                continue

            days_since = (now - ingested).total_seconds() / 86400

            # Grace period: no decay in the first 7 days
            if days_since <= GRACE_PERIOD_DAYS:
                conn.execute(
                    "UPDATE articles SET relevance_weight = 1.0 WHERE id = ?",
                    (row["id"],),
                )
                continue

            decay_days = days_since - GRACE_PERIOD_DAYS

            # Choose decay rate based on article properties
            if rating is not None and rating < 0:
                # Disliked: fastest decay
                rate = config.decay_rate_disliked
            elif row["is_vip"]:
                # VIP source: slowest decay
                rate = config.decay_rate_vip
            else:
                # Default decay
                rate = config.decay_rate_default

            weight = max(MIN_WEIGHT, rate ** decay_days)

            conn.execute(
                "UPDATE articles SET relevance_weight = ? WHERE id = ?",
                (weight, row["id"]),
            )
            updated += 1
            if weight < config.decay_threshold:
                decayed += 1

        conn.commit()
        logger.info(
            "Decay recalculation: %d updated, %d immune, %d below threshold",
            updated, immune, decayed,
        )
        return {
            "total": len(rows),
            "updated": updated,
            "immune": immune,
            "decayed_below_threshold": decayed,
        }
    finally:
        conn.close()
