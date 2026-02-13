"""Email / newsletter ingestion — parse .eml files, extract content."""

import email
import logging
import re
from datetime import datetime
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from lxml import etree
from lxml.html import fromstring, tostring
from markdownify import markdownify as md
from readability import Document

logger = logging.getLogger(__name__)

# UTM and tracking query parameters to strip from links
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "mc_cid", "mc_eid",  # Mailchimp
    "ref", "ref_src",
    "s", "sref",  # Substack
}


def _strip_tracking_pixels(html: str) -> str:
    """Remove 1x1 tracking pixel images from HTML."""
    try:
        tree = fromstring(html)
    except etree.ParserError:
        return html

    for img in list(tree.iter("img")):
        src = img.get("src", "")
        w = img.get("width", "")
        h = img.get("height", "")
        style = img.get("style", "")

        is_pixel = False

        # Explicit 1x1 dimensions
        if (w == "1" or w == "0") and (h == "1" or h == "0"):
            is_pixel = True
        # Hidden via CSS
        if "display:none" in style.replace(" ", "") or "visibility:hidden" in style.replace(" ", ""):
            is_pixel = True
        # Common tracking domains/patterns
        tracking_patterns = [
            "open.substack.com",
            "list-manage.com/track",
            "mailchimp.com/track",
            "email.mg.",
            "/beacon",
            "/track/open",
            "/pixel",
            "trk.klclick",
        ]
        if any(pat in src.lower() for pat in tracking_patterns):
            is_pixel = True

        if is_pixel:
            parent = img.getparent()
            if parent is not None:
                parent.remove(img)

    return tostring(tree, encoding="unicode")


def _strip_utm_params(html: str) -> str:
    """Remove UTM and tracking query params from all links."""
    try:
        tree = fromstring(html)
    except etree.ParserError:
        return html

    for a in tree.iter("a"):
        href = a.get("href", "")
        if not href or "?" not in href:
            continue
        parsed = urlparse(href)
        params = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
        if len(cleaned) != len(params):
            new_query = urlencode(cleaned, doseq=True)
            a.set("href", urlunparse(parsed._replace(query=new_query)))

    return tostring(tree, encoding="unicode")


def _extract_html_body(msg: email.message.EmailMessage) -> str | None:
    """Extract the best HTML body from an email message.

    Prefers text/html over text/plain. Handles multipart messages.
    """
    # Try to get HTML part first
    if msg.is_multipart():
        html_parts = []
        plain_parts = []
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                payload = part.get_content()
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    payload = payload.decode(charset, errors="replace")
                html_parts.append(payload)
            elif ct == "text/plain":
                payload = part.get_content()
                if isinstance(payload, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    payload = payload.decode(charset, errors="replace")
                plain_parts.append(payload)

        if html_parts:
            return html_parts[0]
        if plain_parts:
            # Wrap plain text in basic HTML
            text = plain_parts[0]
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return f"<html><body><pre>{escaped}</pre></body></html>"
    else:
        ct = msg.get_content_type()
        payload = msg.get_content()
        if isinstance(payload, bytes):
            charset = msg.get_content_charset() or "utf-8"
            payload = payload.decode(charset, errors="replace")

        if ct == "text/html":
            return payload
        elif ct == "text/plain":
            escaped = payload.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return f"<html><body><pre>{escaped}</pre></body></html>"

    return None


def parse_eml(source: str | Path | bytes) -> dict:
    """Parse an .eml file and extract content as clean markdown.

    Args:
        source: File path (str or Path) or raw bytes of the .eml content.

    Returns:
        Dict with keys: title, author, content_md, url, published_at, email_sender

    Raises:
        ValueError: If the email can't be parsed or has no content.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        raw = path.read_bytes()
    else:
        raw = source

    msg = email.message_from_bytes(raw, policy=policy.default)

    # --- Extract sender info ---
    from_header = msg.get("From", "")
    sender_name, sender_email = parseaddr(from_header)
    if not sender_name:
        # Use the part before @ as a fallback name
        sender_name = sender_email.split("@")[0] if sender_email else "Unknown"

    # --- Extract subject as title ---
    title = msg.get("Subject", "Untitled Email")
    # Clean up encoding artifacts
    title = title.strip()
    if not title:
        title = "Untitled Email"

    # --- Extract date ---
    published_at = None
    date_header = msg.get("Date")
    if date_header:
        try:
            published_at = parsedate_to_datetime(date_header)
        except (ValueError, TypeError):
            logger.warning("Failed to parse email Date header: %s", date_header)

    # --- Extract HTML body ---
    html_body = _extract_html_body(msg)
    if not html_body:
        raise ValueError("Email has no text/html or text/plain content")

    # --- Clean up email-specific artifacts ---
    html_body = _strip_tracking_pixels(html_body)
    html_body = _strip_utm_params(html_body)

    # --- Run through readability to extract main content ---
    doc = Document(html_body)
    content_html = doc.summary()

    # --- Strip layout tables (same as web.py) ---
    from tiro.ingestion.web import _strip_layout_tables
    content_html = _strip_layout_tables(content_html)

    # --- Convert to markdown ---
    content_md = md(
        content_html,
        heading_style="ATX",
        bullets="-",
        wrap=False,
    )

    # Collapse runs of 3+ blank lines into 2
    content_md = re.sub(r"\n{3,}", "\n\n", content_md).strip()

    if not content_md or len(content_md) < 20:
        raise ValueError(f"Extracted content too short ({len(content_md)} chars)")

    return {
        "title": title,
        "author": sender_name,
        "content_md": content_md,
        "url": "",  # Emails don't have URLs
        "published_at": published_at,
        "email_sender": sender_email,
    }
