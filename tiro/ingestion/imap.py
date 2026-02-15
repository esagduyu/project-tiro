"""IMAP inbox check — fetch unseen emails from a label and ingest them."""

import imaplib
import logging

from tiro.config import TiroConfig
from tiro.ingestion.email import parse_eml
from tiro.ingestion.processor import process_article
from tiro.database import get_connection

logger = logging.getLogger(__name__)


def check_imap_inbox(config: TiroConfig) -> dict:
    """Connect to IMAP, fetch unseen messages from the configured label, and ingest.

    Returns a summary dict:
        {fetched, processed, skipped, failed, articles: [{id, title}]}
    """
    if not config.imap_user or not config.imap_password:
        raise ValueError(
            "IMAP not configured. Set imap_user and imap_password in config.yaml, "
            "or run: tiro setup-email"
        )

    result = {
        "fetched": 0,
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "articles": [],
        "errors": [],
    }

    # Connect
    try:
        imap = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
    except (ConnectionRefusedError, OSError) as e:
        raise RuntimeError(
            f"Could not connect to IMAP server at {config.imap_host}:{config.imap_port}: {e}"
        ) from e

    try:
        imap.login(config.imap_user, config.imap_password)
    except imaplib.IMAP4.error as e:
        imap.logout()
        raise RuntimeError(
            f"IMAP login failed for {config.imap_user}. "
            f"For Gmail, use an App Password: https://myaccount.google.com/apppasswords"
        ) from e

    try:
        # Select the label/folder
        status, data = imap.select(config.imap_label, readonly=False)
        if status != "OK":
            raise RuntimeError(
                f"Could not select IMAP label '{config.imap_label}'. "
                f"Create this label in Gmail and forward newsletters to it."
            )

        # Search for unseen messages
        status, msg_ids = imap.search(None, "UNSEEN")
        if status != "OK" or not msg_ids[0]:
            logger.info("No unseen messages in '%s'", config.imap_label)
            return result

        id_list = msg_ids[0].split()
        result["fetched"] = len(id_list)
        logger.info("Found %d unseen messages in '%s'", len(id_list), config.imap_label)

        for msg_id in id_list:
            try:
                _process_imap_message(imap, msg_id, config, result)
            except Exception as e:
                logger.error("Failed to process IMAP message %s: %s", msg_id, e)
                result["failed"] += 1
                result["errors"].append(str(e))

    finally:
        try:
            imap.close()
        except Exception:
            pass
        imap.logout()

    return result


def _process_imap_message(
    imap: imaplib.IMAP4_SSL,
    msg_id: bytes,
    config: TiroConfig,
    result: dict,
) -> None:
    """Fetch and process a single IMAP message."""
    status, msg_data = imap.fetch(msg_id, "(RFC822)")
    if status != "OK" or not msg_data or not msg_data[0]:
        raise RuntimeError(f"Could not fetch message {msg_id}")

    raw_email = msg_data[0][1]

    # Parse with existing email parser
    try:
        extracted = parse_eml(raw_email)
    except ValueError as e:
        logger.warning("Skipping unparseable email: %s", e)
        result["failed"] += 1
        result["errors"].append(f"Parse error: {e}")
        return

    # Check for duplicates (title + sender)
    conn = get_connection(config.db_path)
    try:
        existing = conn.execute(
            "SELECT a.id, a.title FROM articles a "
            "JOIN sources s ON a.source_id = s.id "
            "WHERE a.title = ? AND s.email_sender = ?",
            (extracted["title"], extracted["email_sender"]),
        ).fetchone()
    finally:
        conn.close()

    if existing:
        logger.info("Duplicate email skipped: '%s'", extracted["title"])
        result["skipped"] += 1
        # Still mark as seen so we don't re-fetch
        imap.store(msg_id, "+FLAGS", "\\Seen")
        return

    # Process article through full pipeline
    try:
        article = process_article(
            title=extracted["title"],
            author=extracted["author"],
            content_md=extracted["content_md"],
            url=extracted["url"],
            config=config,
            published_at=extracted["published_at"],
            email_sender=extracted["email_sender"],
        )
    except Exception as e:
        logger.error("Failed to ingest email '%s': %s", extracted["title"], e)
        result["failed"] += 1
        result["errors"].append(f"Ingest error for '{extracted['title']}': {e}")
        # Leave as unseen for retry
        imap.store(msg_id, "-FLAGS", "\\Seen")
        return

    result["processed"] += 1
    result["articles"].append({"id": article["id"], "title": article["title"]})
    # Mark as seen on success
    imap.store(msg_id, "+FLAGS", "\\Seen")
    logger.info("Ingested email: [%d] %s", article["id"], article["title"])
