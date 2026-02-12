"""Web page ingestion — fetch, extract, convert to markdown."""

import logging
import re

import httpx
from markdownify import markdownify as md
from readability import Document

logger = logging.getLogger(__name__)


async def fetch_and_extract(url: str) -> dict:
    """Fetch a web page and extract its main content as clean markdown.

    Returns dict with keys: title, author, content_md, url
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": "Tiro/0.1 (reading assistant)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        html = response.text

    doc = Document(html)
    title = doc.title()
    content_html = doc.summary()

    # Convert to clean markdown — preserves links and code blocks by default
    content_md = md(
        content_html,
        heading_style="ATX",
        bullets="-",
        wrap=False,
    )

    # Collapse runs of 3+ blank lines into 2
    content_md = re.sub(r"\n{3,}", "\n\n", content_md).strip()

    return {
        "title": title,
        "author": None,  # readability doesn't extract author; Haiku will in Checkpoint 0.3
        "content_md": content_md,
        "url": url,
    }
