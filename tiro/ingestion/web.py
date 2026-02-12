"""Web page ingestion — fetch, extract, convert to markdown."""

import logging
import re

import httpx
from lxml import etree
from lxml.html import fromstring, tostring
from markdownify import markdownify as md
from readability import Document

logger = logging.getLogger(__name__)

# Tags used for layout tables — strip these so markdownify doesn't
# render them as markdown tables (common on old sites like paulgraham.com)
_LAYOUT_TAGS = {"table", "tbody", "thead", "tfoot", "tr", "td", "th"}


def _strip_layout_tables(html: str) -> str:
    """Unwrap layout tables, keeping their inner content intact."""
    try:
        tree = fromstring(html)
    except etree.ParserError:
        return html

    for tag in _LAYOUT_TAGS:
        for el in tree.iter(tag):
            el.drop_tag()  # removes the tag but keeps children and text

    # Remove spacer/nav images (1x1 pixels, image maps, tiny icons)
    for img in list(tree.iter("img")):
        usemap = img.get("usemap")
        ismap = img.get("ismap")
        if usemap is not None or ismap is not None:
            img.drop_tree()
            continue
        src = img.get("src", "")
        # Remove 1x1 spacer gifs (by attribute or filename)
        w = img.get("width", "")
        h = img.get("height", "")
        if w == "1" or h == "1" or "trans_1x1" in src or "spacer" in src:
            img.drop_tree()

    # Remove image map definitions
    for m in tree.iter("map"):
        m.drop_tree()

    return tostring(tree, encoding="unicode")


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

    # Strip layout tables (common on old-school sites) before markdown conversion
    content_html = _strip_layout_tables(content_html)

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
