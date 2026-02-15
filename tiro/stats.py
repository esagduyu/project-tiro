"""Reading stats tracking and aggregation for Tiro."""

import logging
from datetime import date, datetime, timedelta

from tiro.config import TiroConfig
from tiro.database import get_connection

logger = logging.getLogger(__name__)


def update_stat(config: TiroConfig, field: str, increment: int = 1) -> None:
    """Upsert today's reading_stats row and increment the given field.

    Args:
        field: One of 'articles_saved', 'articles_read', 'articles_rated', 'total_reading_time_min'.
        increment: Amount to add (default 1).
    """
    today = date.today().isoformat()
    conn = get_connection(config.db_path)
    try:
        conn.execute(
            f"""INSERT INTO reading_stats (date, {field})
                VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET {field} = {field} + ?""",
            (today, increment, increment),
        )
        conn.commit()
    finally:
        conn.close()


def get_stats(config: TiroConfig, period: str = "month") -> dict:
    """Query and aggregate reading stats for the given period.

    Args:
        period: 'week' (7 days), 'month' (30 days), or 'all'.

    Returns dict with daily_counts, top_tags, top_sources, reading_streak, totals.
    """
    conn = get_connection(config.db_path)
    try:
        # Determine date range
        today = date.today()
        if period == "week":
            start_date = today - timedelta(days=6)
        elif period == "month":
            start_date = today - timedelta(days=29)
        else:
            start_date = None

        # --- Daily counts ---
        if start_date:
            rows = conn.execute(
                """SELECT date, articles_saved, articles_read, articles_rated,
                          total_reading_time_min
                   FROM reading_stats
                   WHERE date >= ?
                   ORDER BY date""",
                (start_date.isoformat(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT date, articles_saved, articles_read, articles_rated,
                          total_reading_time_min
                   FROM reading_stats
                   ORDER BY date"""
            ).fetchall()

        daily_counts = [dict(r) for r in rows]

        # Fill in missing dates with zeros for the period
        if start_date:
            existing = {r["date"] for r in daily_counts}
            filled = []
            d = start_date
            while d <= today:
                ds = d.isoformat()
                if ds in existing:
                    filled.append(next(r for r in daily_counts if r["date"] == ds))
                else:
                    filled.append({
                        "date": ds,
                        "articles_saved": 0,
                        "articles_read": 0,
                        "articles_rated": 0,
                        "total_reading_time_min": 0,
                    })
                d += timedelta(days=1)
            daily_counts = filled

        # --- Totals ---
        totals = {
            "articles_saved": sum(d["articles_saved"] for d in daily_counts),
            "articles_read": sum(d["articles_read"] for d in daily_counts),
            "articles_rated": sum(d["articles_rated"] for d in daily_counts),
            "total_reading_time_min": sum(d["total_reading_time_min"] for d in daily_counts),
        }

        # --- Top tags by frequency (from articles in the period) ---
        if start_date:
            tag_rows = conn.execute(
                """SELECT t.name, COUNT(*) as count
                   FROM tags t
                   JOIN article_tags at ON t.id = at.tag_id
                   JOIN articles a ON a.id = at.article_id
                   WHERE a.ingested_at >= ?
                   GROUP BY t.name
                   ORDER BY count DESC
                   LIMIT 10""",
                (start_date.isoformat(),),
            ).fetchall()
        else:
            tag_rows = conn.execute(
                """SELECT t.name, COUNT(*) as count
                   FROM tags t
                   JOIN article_tags at ON t.id = at.tag_id
                   GROUP BY t.name
                   ORDER BY count DESC
                   LIMIT 10"""
            ).fetchall()

        top_tags = [{"name": r["name"], "count": r["count"]} for r in tag_rows]

        # --- Top sources by engagement ---
        if start_date:
            source_rows = conn.execute(
                """SELECT s.name,
                          COUNT(*) as total_articles,
                          SUM(CASE WHEN a.rating = 2 THEN 1 ELSE 0 END) as loves,
                          SUM(CASE WHEN a.rating = 1 THEN 1 ELSE 0 END) as likes,
                          SUM(CASE WHEN a.rating = -1 THEN 1 ELSE 0 END) as dislikes
                   FROM sources s
                   JOIN articles a ON a.source_id = s.id
                   WHERE a.ingested_at >= ?
                   GROUP BY s.id
                   ORDER BY (loves * 3 + likes * 2 - dislikes * 2) DESC
                   LIMIT 10""",
                (start_date.isoformat(),),
            ).fetchall()
        else:
            source_rows = conn.execute(
                """SELECT s.name,
                          COUNT(*) as total_articles,
                          SUM(CASE WHEN a.rating = 2 THEN 1 ELSE 0 END) as loves,
                          SUM(CASE WHEN a.rating = 1 THEN 1 ELSE 0 END) as likes,
                          SUM(CASE WHEN a.rating = -1 THEN 1 ELSE 0 END) as dislikes
                   FROM sources s
                   JOIN articles a ON a.source_id = s.id
                   GROUP BY s.id
                   ORDER BY (loves * 3 + likes * 2 - dislikes * 2) DESC
                   LIMIT 10"""
            ).fetchall()

        top_sources = [
            {
                "name": r["name"],
                "total_articles": r["total_articles"],
                "loves": r["loves"] or 0,
                "likes": r["likes"] or 0,
                "dislikes": r["dislikes"] or 0,
            }
            for r in source_rows
        ]

        # --- Reading streak ---
        streak = _calculate_streak(conn)

        return {
            "period": period,
            "daily_counts": daily_counts,
            "totals": totals,
            "top_tags": top_tags,
            "top_sources": top_sources,
            "reading_streak": streak,
        }
    finally:
        conn.close()


def _calculate_streak(conn) -> int:
    """Calculate consecutive days with at least one article read, ending today or yesterday."""
    rows = conn.execute(
        """SELECT date FROM reading_stats
           WHERE articles_read > 0
           ORDER BY date DESC"""
    ).fetchall()

    if not rows:
        return 0

    dates = [date.fromisoformat(r["date"]) for r in rows]
    today = date.today()

    # Streak must include today or yesterday to be "current"
    if dates[0] < today - timedelta(days=1):
        return 0

    streak = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            streak += 1
        else:
            break

    return streak
