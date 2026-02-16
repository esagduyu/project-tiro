"""Settings API routes."""

import logging
import os
import re
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask_password(pw: str | None) -> str | None:
    """Mask a password for display, showing first 2 and last 2 chars."""
    if not pw:
        return None
    if len(pw) <= 4:
        return "****"
    return pw[:2] + "*" * (len(pw) - 4) + pw[-2:]


@router.get("/email")
async def get_email_settings(request: Request):
    """Get current email configuration (passwords masked)."""
    config = request.app.state.config
    return {
        "success": True,
        "data": {
            "smtp_configured": bool(config.smtp_user and config.smtp_password),
            "smtp_host": config.smtp_host,
            "smtp_port": config.smtp_port,
            "smtp_user": config.smtp_user,
            "smtp_password_masked": _mask_password(config.smtp_password),
            "smtp_use_tls": config.smtp_use_tls,
            "digest_email": config.digest_email,
            "imap_configured": bool(config.imap_user and config.imap_password),
            "imap_host": config.imap_host,
            "imap_port": config.imap_port,
            "imap_user": config.imap_user,
            "imap_password_masked": _mask_password(config.imap_password),
            "imap_label": config.imap_label,
            "imap_enabled": config.imap_enabled,
            "imap_sync_interval": config.imap_sync_interval,
        },
    }


class EmailSettingsUpdate(BaseModel):
    gmail_address: str | None = None
    app_password: str | None = None
    enable_send: bool = False
    enable_receive: bool = False
    imap_label: str = "tiro"
    imap_sync_interval: int = 15


@router.post("/email")
async def update_email_settings(body: EmailSettingsUpdate, request: Request):
    """Update email configuration in config.yaml and reload."""
    config = request.app.state.config

    if not body.gmail_address or not body.app_password:
        raise HTTPException(status_code=400, detail="Gmail address and app password are required")

    if not body.enable_send and not body.enable_receive:
        raise HTTPException(status_code=400, detail="Select at least one feature (send or receive)")

    # Update config.yaml
    config_path = Path("config.yaml")
    if not config_path.exists():
        raise HTTPException(status_code=500, detail="config.yaml not found")

    config_data = yaml.safe_load(config_path.read_text()) or {}

    if body.enable_send:
        config_data["smtp_host"] = "smtp.gmail.com"
        config_data["smtp_port"] = 587
        config_data["smtp_user"] = body.gmail_address
        config_data["smtp_password"] = body.app_password
        config_data["smtp_use_tls"] = True
        config_data["digest_email"] = body.gmail_address

    if body.enable_receive:
        config_data["imap_host"] = "imap.gmail.com"
        config_data["imap_port"] = 993
        config_data["imap_user"] = body.gmail_address
        config_data["imap_password"] = body.app_password
        config_data["imap_label"] = body.imap_label
        config_data["imap_enabled"] = True
        config_data["imap_sync_interval"] = body.imap_sync_interval

    config_path.write_text(yaml.dump(config_data, default_flow_style=False))

    # Update live config
    if body.enable_send:
        config.smtp_host = "smtp.gmail.com"
        config.smtp_port = 587
        config.smtp_user = body.gmail_address
        config.smtp_password = body.app_password
        config.smtp_use_tls = True
        config.digest_email = body.gmail_address

    if body.enable_receive:
        config.imap_host = "imap.gmail.com"
        config.imap_port = 993
        config.imap_user = body.gmail_address
        config.imap_password = body.app_password
        config.imap_label = body.imap_label
        config.imap_enabled = True
        config.imap_sync_interval = body.imap_sync_interval

    logger.info("Email settings updated: send=%s, receive=%s", body.enable_send, body.enable_receive)

    return {
        "success": True,
        "data": {
            "smtp_configured": body.enable_send,
            "imap_configured": body.enable_receive,
            "gmail_address": body.gmail_address,
            "imap_label": body.imap_label if body.enable_receive else None,
        },
    }


@router.get("/tts")
async def get_tts_settings(request: Request):
    """Get current TTS configuration."""
    config = request.app.state.config
    return {
        "success": True,
        "data": {
            "tts_configured": bool(config.openai_api_key),
            "openai_api_key_masked": _mask_password(config.openai_api_key),
            "tts_voice": config.tts_voice,
            "tts_model": config.tts_model,
        },
    }


class TTSSettingsUpdate(BaseModel):
    openai_api_key: str | None = None
    tts_voice: str = "nova"
    tts_model: str = "tts-1"


@router.post("/tts")
async def update_tts_settings(body: TTSSettingsUpdate, request: Request):
    """Update TTS configuration."""
    config = request.app.state.config

    if not body.openai_api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key is required")

    config_path = Path("config.yaml")
    if not config_path.exists():
        raise HTTPException(status_code=500, detail="config.yaml not found")

    config_data = yaml.safe_load(config_path.read_text()) or {}
    config_data["openai_api_key"] = body.openai_api_key
    config_data["tts_voice"] = body.tts_voice
    config_data["tts_model"] = body.tts_model
    config_path.write_text(yaml.dump(config_data, default_flow_style=False))

    # Update live config
    config.openai_api_key = body.openai_api_key
    config.tts_voice = body.tts_voice
    config.tts_model = body.tts_model
    os.environ["OPENAI_API_KEY"] = body.openai_api_key

    logger.info("TTS settings updated: voice=%s, model=%s", body.tts_voice, body.tts_model)

    return {
        "success": True,
        "data": {
            "tts_configured": True,
            "tts_voice": body.tts_voice,
            "tts_model": body.tts_model,
        },
    }


# Required --tiro-* CSS variables for theme validation
REQUIRED_THEME_VARS = [
    "--tiro-bg", "--tiro-bg-surface", "--tiro-bg-hover",
    "--tiro-fg", "--tiro-fg-secondary", "--tiro-muted",
    "--tiro-border", "--tiro-accent", "--tiro-accent-hover",
    "--tiro-secondary", "--tiro-secondary-hover",
    "--tiro-gold", "--tiro-gold-hover",
    "--tiro-sidebar-bg", "--tiro-sidebar-active",
    "--tiro-tier-must-read", "--tiro-tier-summary", "--tiro-tier-discard",
    "--tiro-rate-love", "--tiro-rate-like", "--tiro-rate-dislike",
]


def _list_available_themes(config) -> list[dict]:
    """List available themes from built-in and library theme directories."""
    themes = []

    # Built-in themes
    builtin_dir = Path(__file__).parent.parent / "frontend" / "static" / "themes"
    if builtin_dir.exists():
        for css_file in sorted(builtin_dir.glob("*.css")):
            themes.append({
                "name": css_file.stem,
                "path": f"/static/themes/{css_file.name}",
                "builtin": True,
            })

    # Library custom themes
    custom_dir = config.library / "themes"
    if custom_dir.exists():
        for css_file in sorted(custom_dir.glob("*.css")):
            if not any(t["name"] == css_file.stem for t in themes):
                themes.append({
                    "name": css_file.stem,
                    "path": f"/library/themes/{css_file.name}",
                    "builtin": False,
                })

    return themes


def _validate_theme_css(css_content: str) -> list[str]:
    """Check CSS for required --tiro-* variables. Returns list of missing vars."""
    missing = []
    for var in REQUIRED_THEME_VARS:
        if var + ":" not in css_content:
            missing.append(var)
    return missing


@router.get("/appearance")
async def get_appearance_settings(request: Request):
    """Get current appearance settings (themes, page size)."""
    config = request.app.state.config
    themes = _list_available_themes(config)
    return {
        "success": True,
        "data": {
            "theme_light": config.theme_light,
            "theme_dark": config.theme_dark,
            "inbox_page_size": config.inbox_page_size,
            "themes": themes,
        },
    }


class AppearanceUpdate(BaseModel):
    theme_light: str | None = None
    theme_dark: str | None = None
    inbox_page_size: int | None = None


@router.post("/appearance")
async def update_appearance_settings(body: AppearanceUpdate, request: Request):
    """Update appearance settings (theme selections, page size)."""
    config = request.app.state.config

    config_path = Path("config.yaml")
    if not config_path.exists():
        raise HTTPException(status_code=500, detail="config.yaml not found")

    config_data = yaml.safe_load(config_path.read_text()) or {}

    if body.theme_light is not None:
        config_data["theme_light"] = body.theme_light
        config.theme_light = body.theme_light
    if body.theme_dark is not None:
        config_data["theme_dark"] = body.theme_dark
        config.theme_dark = body.theme_dark
    if body.inbox_page_size is not None:
        if body.inbox_page_size not in (25, 50, 100, 0):
            raise HTTPException(status_code=400, detail="Page size must be 25, 50, or 100 (0 for all)")
        config_data["inbox_page_size"] = body.inbox_page_size
        config.inbox_page_size = body.inbox_page_size

    config_path.write_text(yaml.dump(config_data, default_flow_style=False))

    logger.info(
        "Appearance updated: light=%s, dark=%s, page_size=%s",
        config.theme_light, config.theme_dark, config.inbox_page_size,
    )

    return {
        "success": True,
        "data": {
            "theme_light": config.theme_light,
            "theme_dark": config.theme_dark,
            "inbox_page_size": config.inbox_page_size,
        },
    }


class ThemeImport(BaseModel):
    name: str
    css: str


@router.post("/theme/import")
async def import_theme(body: ThemeImport, request: Request):
    """Import a custom theme CSS file. Validates required --tiro-* variables."""
    config = request.app.state.config

    # Validate name (alphanumeric + hyphens only)
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", body.name):
        raise HTTPException(status_code=400, detail="Theme name must be lowercase alphanumeric with hyphens")

    if len(body.css) < 50:
        raise HTTPException(status_code=400, detail="CSS content too short")

    if len(body.css) > 50000:
        raise HTTPException(status_code=400, detail="CSS content too large (max 50KB)")

    missing = _validate_theme_css(body.css)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required CSS variables: {', '.join(missing[:5])}"
            + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""),
        )

    # Save to library/themes/
    themes_dir = config.library / "themes"
    themes_dir.mkdir(parents=True, exist_ok=True)
    theme_path = themes_dir / f"{body.name}.css"
    theme_path.write_text(body.css)

    logger.info("Custom theme imported: %s (%d bytes)", body.name, len(body.css))

    return {
        "success": True,
        "data": {
            "name": body.name,
            "path": f"/library/themes/{body.name}.css",
        },
    }
