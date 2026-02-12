"""AI metadata extraction using Claude Haiku."""

import json
import logging
import os

import anthropic

from tiro.config import TiroConfig

logger = logging.getLogger(__name__)


def extract_metadata(title: str, content_md: str, config: TiroConfig) -> dict:
    """Extract tags, entities, and summary using Claude Haiku.

    Returns dict with keys: tags (list[str]), entities (list[dict]), summary (str).
    Returns empty defaults if extraction fails or no API key is configured.
    The Anthropic SDK reads ANTHROPIC_API_KEY from the environment automatically.
    """
    empty = {"tags": [], "entities": [], "summary": ""}

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI extraction")
        return empty

    content_truncated = content_md[:2000]

    prompt = (
        "You are analyzing a saved article for a personal reading library. "
        "Extract structured metadata.\n\n"
        f"Article title: {title}\n"
        f"Article content: {content_truncated}\n\n"
        "Respond with JSON only, no other text:\n"
        "{\n"
        '  "tags": ["tag1", "tag2", ...],\n'
        '  "entities": [\n'
        '    {"name": "Entity Name", "type": "person|company|organization|product"}\n'
        "  ],\n"
        '  "summary": "2-3 sentence summary of the article\'s key points."\n'
        "}"
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=config.haiku_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(text)

        tags = data.get("tags", [])
        entities = data.get("entities", [])
        summary = data.get("summary", "")

        if not isinstance(tags, list):
            tags = []
        if not isinstance(entities, list):
            entities = []
        if not isinstance(summary, str):
            summary = ""

        # Normalize tags: lowercase, stripped, max 8
        tags = [str(t).lower().strip() for t in tags if t][:8]

        # Validate entity structure
        valid_entities = []
        for e in entities:
            if isinstance(e, dict) and "name" in e and "type" in e:
                valid_entities.append({
                    "name": str(e["name"]).strip(),
                    "type": str(e["type"]).strip().lower(),
                })

        logger.info(
            "Extracted %d tags, %d entities for '%s'",
            len(tags), len(valid_entities), title,
        )
        return {"tags": tags, "entities": valid_entities, "summary": summary}

    except Exception as e:
        logger.error("AI extraction failed for '%s': %s", title, e)
        return empty
