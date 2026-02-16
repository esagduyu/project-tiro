"""Settings API routes."""

import logging
import os
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
        },
    }


class EmailSettingsUpdate(BaseModel):
    gmail_address: str | None = None
    app_password: str | None = None
    enable_send: bool = False
    enable_receive: bool = False
    imap_label: str = "tiro"


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
