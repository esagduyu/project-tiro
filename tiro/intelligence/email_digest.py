"""Email delivery of daily digests."""

import logging
import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tiro.config import TiroConfig
from tiro.intelligence.digest import generate_digest, get_cached_digest

logger = logging.getLogger(__name__)


def send_digest_email(config: TiroConfig, all_sections: bool = False) -> dict:
    """Generate (or retrieve cached) today's digest and send it via email.

    Args:
        config: Tiro configuration
        all_sections: If True, include all 3 digest sections (by_topic, by_entity, ranked).
                      If False (default), send only the ranked digest.

    Returns a summary dict with status info.
    """
    if not config.digest_email:
        raise ValueError("No digest_email configured. Set digest_email in config.yaml.")

    today = date.today().isoformat()

    if all_sections:
        # Get or generate all 3 sections (reuse cache if <24h old)
        cached = get_cached_digest(config, today)
        if cached and "ranked" in cached:
            created_at = next(iter(cached.values()))["created_at"]
            age_hours = (datetime.utcnow() - datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
            if age_hours < 24:
                all_data = cached
                logger.info("Using cached digest (%.1fh old) for email", age_hours)
            else:
                logger.info("Cached digest too old (%.1fh), regenerating", age_hours)
                all_data = generate_digest(config)
                created_at = next(iter(all_data.values()))["created_at"]
        else:
            logger.info("No cached digest found, generating fresh")
            all_data = generate_digest(config)
            created_at = next(iter(all_data.values()))["created_at"]

        # Combine sections: by_topic -> by_entity -> ranked
        section_order = [
            ("by_topic", "Grouped by Topic"),
            ("by_entity", "Grouped by Entity"),
            ("ranked", "Ranked by Importance"),
        ]
        parts = []
        for key, heading in section_order:
            if key in all_data and all_data[key].get("content"):
                parts.append(f"## {heading}\n\n{all_data[key]['content']}")
        digest_content = "\n\n---\n\n".join(parts) if parts else "*No digest content available.*"
    else:
        # Get or generate the ranked digest only (reuse cache if <24h old)
        cached = get_cached_digest(config, today, "ranked")
        if cached and "ranked" in cached:
            created_at = cached["ranked"]["created_at"]
            age_hours = (datetime.utcnow() - datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
            if age_hours < 24:
                digest_content = cached["ranked"]["content"]
                logger.info("Using cached ranked digest (%.1fh old) for email", age_hours)
            else:
                logger.info("Cached ranked digest too old (%.1fh), regenerating", age_hours)
                result = generate_digest(config)
                digest_content = result["ranked"]["content"]
                created_at = result["ranked"]["created_at"]
        else:
            logger.info("No cached ranked digest found, generating fresh")
            result = generate_digest(config)
            digest_content = result["ranked"]["content"]
            created_at = result["ranked"]["created_at"]

    # Convert markdown digest to HTML email
    html_body = _digest_to_html(digest_content, config)
    plain_body = digest_content

    # Determine sender address
    from_addr = config.smtp_user or "tiro@localhost"
    from_display = f"Tiro <{from_addr}>"

    # Build the email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Tiro Daily Digest — {_format_date(today)}"
    msg["From"] = from_display
    msg["To"] = config.digest_email

    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Send via SMTP
    try:
        if config.smtp_user and config.smtp_password:
            # Authenticated SMTP (e.g. Gmail with app password)
            if config.smtp_use_tls:
                with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                    server.starttls()
                    server.login(config.smtp_user, config.smtp_password)
                    server.sendmail(from_addr, [config.digest_email], msg.as_string())
            else:
                with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port) as server:
                    server.login(config.smtp_user, config.smtp_password)
                    server.sendmail(from_addr, [config.digest_email], msg.as_string())
        else:
            # Plain SMTP (e.g. local mailhog)
            with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
                server.sendmail(from_addr, [config.digest_email], msg.as_string())
        logger.info("Digest email sent to %s via %s:%d", config.digest_email, config.smtp_host, config.smtp_port)
    except (ConnectionRefusedError, OSError) as e:
        raise RuntimeError(
            f"Could not connect to SMTP server at {config.smtp_host}:{config.smtp_port}. "
            f"For Gmail, use smtp.gmail.com:587 with an app password. "
            f"For local testing, run: docker run -p 1025:1025 -p 8025:8025 mailhog/mailhog"
        ) from e
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            f"SMTP authentication failed for {config.smtp_user}. "
            f"For Gmail, use an App Password (not your regular password): "
            f"https://myaccount.google.com/apppasswords"
        ) from e

    return {
        "sent_to": config.digest_email,
        "subject": msg["Subject"],
        "digest_date": today,
        "digest_generated_at": created_at,
        "smtp": f"{config.smtp_host}:{config.smtp_port}",
    }


def _format_date(iso_date: str) -> str:
    """Format YYYY-MM-DD as 'February 15, 2026'."""
    d = datetime.strptime(iso_date, "%Y-%m-%d")
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def _get_logo_data_uri() -> str:
    """Get the Tiro logo as a base64 data URI for inline email embedding."""
    import base64
    from pathlib import Path
    logo_path = Path(__file__).parent.parent / "frontend" / "static" / "logo-128.png"
    if logo_path.exists():
        data = base64.b64encode(logo_path.read_bytes()).decode()
        return f"data:image/png;base64,{data}"
    return ""


# Roman color palette (matches papyrus theme)
_COLORS = {
    "bg": "#FAF6F0",          # papyrus cream
    "surface": "#FFFFFF",
    "fg": "#3D3630",          # warm brown text
    "fg_secondary": "#6B6560",
    "muted": "#9C9590",
    "accent": "#C45B3E",      # terra cotta
    "gold": "#B8943E",        # warm gold for links
    "border": "#E8E0D8",
    "hr": "#D9D0C7",
}


def _digest_to_html(markdown_content: str, config: TiroConfig) -> str:
    """Convert a markdown digest to a clean HTML email body."""
    import re

    # Use localhost for article links (0.0.0.0 won't resolve in email clients)
    host = "localhost" if config.host == "0.0.0.0" else config.host
    base_url = f"http://{host}:{config.port}"
    c = _COLORS
    html = markdown_content

    # Convert markdown links [text](/articles/123) to absolute HTML links
    html = re.sub(
        r'\[([^\]]+)\]\(/articles/(\d+)\)',
        rf'<a href="{base_url}/articles/\2" style="color: {c["gold"]}; text-decoration: none; font-weight: 500;">\1</a>',
        html,
    )

    # Convert remaining markdown links [text](url)
    html = re.sub(
        r'\[([^\]]+)\]\((https?://[^\)]+)\)',
        rf'<a href="\2" style="color: {c["gold"]}; text-decoration: none;">\1</a>',
        html,
    )

    # Convert markdown headings
    html = re.sub(
        r'^#### (.+)$',
        rf'<h4 style="margin: 1em 0 0.3em; color: {c["fg"]}; font-size: 14px;">\1</h4>',
        html, flags=re.MULTILINE,
    )
    html = re.sub(
        r'^### (.+)$',
        rf'<h3 style="margin: 1.2em 0 0.4em; color: {c["fg"]}; font-size: 16px;">\1</h3>',
        html, flags=re.MULTILINE,
    )
    html = re.sub(
        r'^## (.+)$',
        rf'<h2 style="margin: 1.5em 0 0.5em; color: {c["accent"]}; font-size: 18px; '
        rf'padding-bottom: 6px; border-bottom: 1px solid {c["border"]};">\1</h2>',
        html, flags=re.MULTILINE,
    )

    # Bold and italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # List items
    html = re.sub(
        r'^- (.+)$',
        rf'<li style="margin-bottom: 0.3em; color: {c["fg_secondary"]};">\1</li>',
        html, flags=re.MULTILINE,
    )

    # Wrap consecutive <li> items in <ul>
    html = re.sub(
        r'((?:<li[^>]*>.*?</li>\n?)+)',
        r'<ul style="padding-left: 1.5em; margin: 0.5em 0;">\1</ul>',
        html,
    )

    # Numbered list items
    html = re.sub(
        r'^(\d+)\. (.+)$',
        rf'<li style="margin-bottom: 0.3em; color: {c["fg_secondary"]};">\2</li>',
        html, flags=re.MULTILINE,
    )

    # Paragraphs: wrap remaining plain lines
    lines = html.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append('')
        elif stripped.startswith('<'):
            result.append(line)
        else:
            result.append(
                f'<p style="margin: 0.5em 0; line-height: 1.6; color: {c["fg_secondary"]};">{stripped}</p>'
            )
    html = '\n'.join(result)

    # Horizontal rules
    html = html.replace(
        '---',
        f'<hr style="border: none; border-top: 1px solid {c["hr"]}; margin: 1.5em 0;">',
    )

    today_str = _format_date(str(date.today()))
    logo_uri = _get_logo_data_uri()
    logo_html = (
        f'<img src="{logo_uri}" alt="Tiro" width="36" height="36" '
        f'style="display: block; margin: 0 auto 6px; border-radius: 6px;">'
        if logo_uri else
        '<div style="font-size: 28px; margin-bottom: 4px;">&#8266;</div>'
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Georgia, 'Times New Roman', serif; max-width: 640px; margin: 0 auto; padding: 20px; color: {c["fg"]}; background: {c["bg"]}; line-height: 1.6;">
    <div style="background: {c["surface"]}; border-radius: 6px; padding: 28px 32px; border: 1px solid {c["border"]};">
        <div style="text-align: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 2px solid {c["accent"]};">
            {logo_html}
            <h1 style="margin: 0; font-size: 20px; color: {c["fg"]}; letter-spacing: 0.02em; font-weight: 600;">Tiro Daily Digest</h1>
            <p style="margin: 6px 0 0; font-size: 13px; color: {c["muted"]};">{today_str}</p>
        </div>
        {html}
    </div>
    <p style="text-align: center; font-size: 11px; color: {c["muted"]}; margin-top: 16px; font-style: italic;">
        "...without you the oracle was dumb." — Cicero to Tiro, 53 BC
    </p>
    <p style="text-align: center; font-size: 11px; color: {c["muted"]}; margin-top: 4px;">
        Sent by <a href="{base_url}" style="color: {c["gold"]};">Tiro</a> — your reading, organized
    </p>
</body>
</html>"""
