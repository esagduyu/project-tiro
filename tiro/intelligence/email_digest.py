"""Email delivery of daily digests."""

import logging
import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tiro.config import TiroConfig
from tiro.intelligence.digest import generate_digest, get_cached_digest

logger = logging.getLogger(__name__)


def send_digest_email(config: TiroConfig) -> dict:
    """Generate (or retrieve cached) today's digest and send it via email.

    Returns a summary dict with status info.
    """
    if not config.digest_email:
        raise ValueError("No digest_email configured. Set digest_email in config.yaml.")

    today = date.today().isoformat()

    # Get or generate the ranked digest
    cached = get_cached_digest(config, today, "ranked")
    if cached and "ranked" in cached:
        digest_content = cached["ranked"]["content"]
        created_at = cached["ranked"]["created_at"]
    else:
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


def _digest_to_html(markdown_content: str, config: TiroConfig) -> str:
    """Convert a markdown digest to a clean HTML email body."""
    # Simple markdown-to-HTML conversion for email
    # Convert article links from relative to absolute
    base_url = f"http://{config.host}:{config.port}"
    html = markdown_content

    # Convert markdown links [text](/articles/123) to absolute HTML links
    import re
    html = re.sub(
        r'\[([^\]]+)\]\(/articles/(\d+)\)',
        rf'<a href="{base_url}/articles/\2" style="color: #2563eb; text-decoration: none;">\1</a>',
        html,
    )

    # Convert remaining markdown links [text](url)
    html = re.sub(
        r'\[([^\]]+)\]\((https?://[^\)]+)\)',
        r'<a href="\2" style="color: #2563eb; text-decoration: none;">\1</a>',
        html,
    )

    # Convert markdown headings
    html = re.sub(r'^#### (.+)$', r'<h4 style="margin: 1em 0 0.3em; color: #1a1a1a;">\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3 style="margin: 1.2em 0 0.4em; color: #1a1a1a;">\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2 style="margin: 1.5em 0 0.5em; color: #1a1a1a;">\1</h2>', html, flags=re.MULTILINE)

    # Bold and italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)

    # List items
    html = re.sub(r'^- (.+)$', r'<li style="margin-bottom: 0.3em;">\1</li>', html, flags=re.MULTILINE)

    # Wrap consecutive <li> items in <ul>
    html = re.sub(
        r'((?:<li[^>]*>.*?</li>\n?)+)',
        r'<ul style="padding-left: 1.5em; margin: 0.5em 0;">\1</ul>',
        html,
    )

    # Numbered list items
    html = re.sub(r'^(\d+)\. (.+)$', r'<li style="margin-bottom: 0.3em;">\2</li>', html, flags=re.MULTILINE)

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
            result.append(f'<p style="margin: 0.5em 0; line-height: 1.6;">{stripped}</p>')
    html = '\n'.join(result)

    # Horizontal rules
    html = html.replace('---', '<hr style="border: none; border-top: 1px solid #e5e5e5; margin: 1.5em 0;">')

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1a1a1a; background: #fafafa; line-height: 1.6;">
    <div style="background: white; border-radius: 8px; padding: 24px; border: 1px solid #e5e5e5;">
        <div style="text-align: center; margin-bottom: 20px; padding-bottom: 16px; border-bottom: 2px solid #2563eb;">
            <h1 style="margin: 0; font-size: 20px; color: #1a1a1a; letter-spacing: -0.01em;">Tiro Daily Digest</h1>
            <p style="margin: 4px 0 0; font-size: 13px; color: #888;">{_format_date(str(date.today()))}</p>
        </div>
        {html}
    </div>
    <p style="text-align: center; font-size: 11px; color: #aaa; margin-top: 16px;">
        Sent by <a href="{base_url}" style="color: #888;">Tiro</a> — your reading, organized
    </p>
</body>
</html>"""
