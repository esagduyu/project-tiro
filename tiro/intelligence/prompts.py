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
        weight = a.get("relevance_weight", 1.0)
        weight_note = f" | Relevance: {weight:.2f}" if weight < 1.0 else ""
        article_lines.append(
            f"- ID: {a['id']} | Title: \"{a['title']}\" | Source: {a['source']}{vip_marker}{weight_note}\n"
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
- Articles with lower relevance scores (< 1.0) have decayed due to lack of engagement — rank them lower
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


def ingenuity_analysis_prompt(full_article_text: str, source_name: str) -> str:
    """Build the ingenuity/trust analysis prompt for Opus 4.6.

    Args:
        full_article_text: The full markdown text of the article.
        source_name: The name of the source (e.g., "Stratechery").
    """
    return f"""You are a media literacy analyst. Evaluate this article across three dimensions.

Article: {full_article_text}
Source: {source_name}

Respond with JSON only — no markdown fences, no commentary:
{{
  "bias": {{
    "score": 1-10,
    "lean": "left|center-left|center|center-right|right|non-political",
    "indicators": ["list of specific bias indicators found"],
    "missing_perspectives": ["perspectives not represented"]
  }},
  "factual_confidence": {{
    "score": 1-10,
    "well_sourced_claims": ["claims with clear evidence or citations"],
    "unsourced_assertions": ["claims presented as fact without backing"],
    "flags": ["any potential misinformation or misleading framing"]
  }},
  "novelty": {{
    "score": 1-10,
    "assessment": "Brief description of what's new vs. known",
    "novel_claims": ["genuinely new information or synthesis"]
  }},
  "overall_summary": "2-sentence overall assessment of this article's trustworthiness and value."
}}"""


def learned_preferences_prompt(
    loved_articles: list[dict],
    liked_articles: list[dict],
    disliked_articles: list[dict],
    vip_sources: list[str],
    unrated_articles: list[dict],
) -> str:
    """Build the learned-preferences classification prompt for Opus 4.6.

    Args:
        loved_articles: Dicts with keys: title, source, summary (rating 2)
        liked_articles: Dicts with keys: title, source, summary (rating 1)
        disliked_articles: Dicts with keys: title, source, summary (rating -1)
        vip_sources: Names of VIP sources
        unrated_articles: Dicts with keys: id, title, source, summary (to classify)
    """

    def _format_rated(articles: list[dict]) -> str:
        if not articles:
            return "None yet."
        lines = []
        for a in articles:
            lines.append(
                f"- \"{a['title']}\" ({a['source']}): {a['summary'] or 'No summary.'}"
            )
        return "\n".join(lines)

    def _format_unrated(articles: list[dict]) -> str:
        lines = []
        for a in articles:
            lines.append(
                f"- ID: {a['id']} | \"{a['title']}\" ({a['source']}): "
                f"{a['summary'] or 'No summary.'}"
            )
        return "\n".join(lines)

    vip_str = ", ".join(vip_sources) if vip_sources else "None set"

    return f"""You are learning a user's reading preferences to classify new articles.

## Articles the user LOVED (rating: 2)
{_format_rated(loved_articles)}

## Articles the user LIKED (rating: 1)
{_format_rated(liked_articles)}

## Articles the user DISLIKED (rating: -1)
{_format_rated(disliked_articles)}

## VIP Sources (always prioritize)
{vip_str}

## Articles to Classify
{_format_unrated(unrated_articles)}

For each article, classify into one tier:
- "must-read": User would want to read this in full. Matches their interests, from VIP sources, or high-impact content.
- "summary-enough": Worth knowing about but the summary captures sufficient value.
- "discard": Unlikely to interest this user based on their demonstrated preferences.

Respond with JSON only — no markdown fences, no commentary:
{{
  "classifications": [
    {{"article_id": 1, "tier": "must-read", "reason": "brief explanation"}},
    ...
  ]
}}"""
