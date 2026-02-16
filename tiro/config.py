"""Configuration loading for Tiro."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULTS = {
    "library_path": "./tiro-library",
    "host": "127.0.0.1",
    "port": 8000,
    "default_embedding_model": "all-MiniLM-L6-v2",
    "opus_model": "claude-opus-4-6",
    "haiku_model": "claude-haiku-4-5-20251001",
    "decay_rate_default": 0.95,
    "decay_rate_disliked": 0.90,
    "decay_rate_vip": 0.98,
    "decay_threshold": 0.1,
}


@dataclass
class TiroConfig:
    library_path: str = DEFAULTS["library_path"]
    host: str = DEFAULTS["host"]
    port: int = DEFAULTS["port"]
    default_embedding_model: str = DEFAULTS["default_embedding_model"]
    opus_model: str = DEFAULTS["opus_model"]
    haiku_model: str = DEFAULTS["haiku_model"]
    decay_rate_default: float = DEFAULTS["decay_rate_default"]
    decay_rate_disliked: float = DEFAULTS["decay_rate_disliked"]
    decay_rate_vip: float = DEFAULTS["decay_rate_vip"]
    decay_threshold: float = DEFAULTS["decay_threshold"]
    anthropic_api_key: str | None = None
    digest_email: str | None = None
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str | None = None
    imap_password: str | None = None
    imap_label: str = "tiro"
    imap_enabled: bool = False
    imap_sync_interval: int = 0  # minutes, 0 = manual only
    openai_api_key: str | None = None
    tts_voice: str = "nova"
    tts_model: str = "tts-1"

    @property
    def library(self) -> Path:
        return Path(self.library_path).resolve()

    @property
    def articles_dir(self) -> Path:
        return self.library / "articles"

    @property
    def db_path(self) -> Path:
        return self.library / "tiro.db"

    @property
    def chroma_dir(self) -> Path:
        return self.library / "chroma"


def load_config(config_path: str | Path = "config.yaml") -> TiroConfig:
    """Load configuration from a YAML file, falling back to defaults."""
    path = Path(config_path)
    data: dict = {}

    if path.exists():
        logger.info("Loading config from %s", path)
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    else:
        logger.info("No config file found at %s, using defaults", path)

    # Only pass known fields to the dataclass
    known_fields = {f.name for f in TiroConfig.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in known_fields}

    config = TiroConfig(**filtered)

    # Set ANTHROPIC_API_KEY env var from config if not already set
    if config.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = config.anthropic_api_key

    # Set OPENAI_API_KEY env var from config if not already set
    if config.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = config.openai_api_key

    return config
