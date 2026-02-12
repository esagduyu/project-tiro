"""Centralized prompt templates for Tiro's intelligence layer."""


def daily_digest_prompt(
    vip_sources: list[str],
    recent_ratings: list[dict],
    articles: list[dict],
) -> str:
    """Build the daily digest prompt for Opus 4.6.

    Args:
        vip_sources: Names of VIP sources (e.g., ["Stratechery", "Matt Levine"])
        recent_ratings: List of dicts with keys: title, source, rating_label, summary
        articles: List of dicts with keys: id, title, source, is_vip, tags, entities, summary, published_date
    """
    # Format VIP sources
    vip_str = ", ".join(vip_sources) if vip_sources else "None set"

    # Format recent ratings
    if recent_ratings:
        ratings_lines = []
        for r in recent_ratings:
            ratings_lines.append(
                f"- [{r['rating_label']}] \"{r['title']}\" ({r['source']}): {r['summary']}"
            )
        ratings_str = "\n".join(ratings_lines)
    else:
        ratings_str = "No ratings yet."

    # Format articles
    article_lines = []
    for a in articles:
        vip_marker = " [VIP]" if a["is_vip"] else ""
        tags = ", ".join(a["tags"]) if a["tags"] else "none"
        entities = ", ".join(a["entities"]) if a["entities"] else "none"
        article_lines.append(
            f"- ID: {a['id']} | Title: \"{a['title']}\" | Source: {a['source']}{vip_marker}\n"
            f"  Tags: {tags}\n"
            f"  Entities: {entities}\n"
            f"  Published: {a['published_date'] or 'unknown'}\n"
            f"  Summary: {a['summary'] or 'No summary available.'}"
        )
    articles_str = "\n\n".join(article_lines)

    return f"""You are Tiro, a personal reading assistant. Generate a daily digest of the user's saved articles.

## User Context
- VIP sources (always prioritize): {vip_str}
- Recent ratings:
{ratings_str}

## Today's Articles
{articles_str}

## Task
Generate three digest sections in markdown. Each section should be a complete, standalone analysis.

### 1. Ranked by Importance
Order all articles by significance to this reader. Consider:
- VIP sources should be weighted higher
- User's demonstrated interests from ratings
- Timeliness and impact of the content
For each article, include a 1-sentence reason for its position.

### 2. Grouped by Topic
Cluster articles by theme. For each cluster:
- Name the theme
- List articles with brief context
- **Call out cross-references**: where articles discuss the same topic from different angles, reach different conclusions, or where one article's claims contradict another's
- Highlight thematic threads that connect seemingly unrelated articles

### 3. Grouped by Entity
Organize by the key people, companies, and organizations discussed.
Note when the same entity appears across multiple sources with different coverage.
Map relationships between entities when they appear together.

## Formatting Rules
- Format ALL article references as markdown links: [Article Title](/articles/ID) where ID is the article's numeric ID
- Use clear markdown headings and bullet points
- Be insightful — don't just list articles, find the connections and contradictions the reader would miss
- Keep each entry concise but substantive
- For the ranked section, number the entries"""
