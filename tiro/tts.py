"""Text-to-speech generation for Tiro articles using OpenAI TTS API."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import frontmatter
import httpx

from tiro.config import TiroConfig
from tiro.database import get_connection

logger = logging.getLogger(__name__)

# OpenAI TTS has a ~4096 character input limit
MAX_CHUNK_CHARS = 4000


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at paragraph boundaries.

    Splits on double-newline paragraph breaks. If a single paragraph exceeds
    max_chars, falls back to splitting at sentence boundaries ('. ').
    Returns a list of non-empty text chunks.
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph would exceed the limit, flush current chunk
        if current and len(current) + 2 + len(para) > max_chars:
            chunks.append(current.strip())
            current = ""

        # If a single paragraph exceeds max_chars, split at sentence boundaries
        if len(para) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            sentences = re.split(r'(?<=\. )', para)
            sentence_chunk = ""
            for sentence in sentences:
                if sentence_chunk and len(sentence_chunk) + len(sentence) > max_chars:
                    chunks.append(sentence_chunk.strip())
                    sentence_chunk = ""
                sentence_chunk += sentence
            if sentence_chunk.strip():
                current = sentence_chunk
        else:
            if current:
                current += "\n\n" + para
            else:
                current = para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _strip_markdown_for_speech(text: str) -> str:
    """Remove markdown formatting to produce clean text for TTS."""
    # Remove code blocks (fenced)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`([^`]*)`', r'\1', text)
    # Remove images: ![alt](url) -> alt
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Convert links: [text](url) -> text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remove heading markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'___(.+?)___', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # Remove horizontal rules
    text = re.sub(r'^[\-\*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # Remove blockquote markers
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove list markers
    text = re.sub(r'^\s*[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _estimate_mp3_duration(size_bytes: int) -> float:
    """Estimate MP3 duration from file size (~128kbps = 16,000 bytes/sec)."""
    return size_bytes / 16000.0


def _prepare_article_text(article_id: int, config: TiroConfig) -> str:
    """Load article and return clean speech text."""
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT title, markdown_path FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found")
    finally:
        conn.close()

    md_path = config.articles_dir / row["markdown_path"]
    if not md_path.exists():
        raise ValueError(f"Markdown file not found: {md_path}")

    post = frontmatter.load(str(md_path))
    full_text = f"{row['title']}\n\n{post.content}"
    return _strip_markdown_for_speech(full_text)


async def stream_article_audio(
    article_id: int, config: TiroConfig
) -> AsyncGenerator[bytes, None]:
    """Stream TTS audio for an article, caching the result.

    Yields MP3 bytes as they arrive from OpenAI. For articles requiring
    multiple chunks (>4000 chars), streams each chunk sequentially.
    After all bytes are yielded, saves the complete file to disk and
    records metadata in the audio table.

    The browser's <audio> element handles progressive MP3 download natively,
    so playback starts within ~1-2 seconds of the first bytes arriving.
    """
    speech_text = _prepare_article_text(article_id, config)
    chunks = chunk_text(speech_text)
    if not chunks:
        raise ValueError(f"Article {article_id} produced no text chunks")

    logger.info(
        "Streaming TTS for article %d: %d chunks, %d chars",
        article_id, len(chunks), sum(len(c) for c in chunks),
    )

    all_bytes = bytearray()

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, chunk in enumerate(chunks):
            logger.info("  Streaming chunk %d/%d (%d chars)...", i + 1, len(chunks), len(chunk))
            async with client.stream(
                "POST",
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {config.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.tts_model,
                    "input": chunk,
                    "voice": config.tts_voice,
                    "response_format": "mp3",
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    logger.error("OpenAI TTS error %d: %s", response.status_code, body[:500])
                    raise RuntimeError(f"OpenAI TTS API returned {response.status_code}")

                async for data in response.aiter_bytes(chunk_size=8192):
                    all_bytes.extend(data)
                    yield data

    # All chunks streamed — cache the complete file
    audio_dir = config.library / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{article_id}.mp3"
    audio_path.write_bytes(bytes(all_bytes))

    duration = _estimate_mp3_duration(len(all_bytes))
    generated_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection(config.db_path)
    try:
        conn.execute(
            """INSERT INTO audio (article_id, file_path, duration_seconds, voice, model,
                                  file_size_bytes, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(article_id) DO UPDATE SET
                   file_path = excluded.file_path,
                   duration_seconds = excluded.duration_seconds,
                   voice = excluded.voice,
                   model = excluded.model,
                   file_size_bytes = excluded.file_size_bytes,
                   generated_at = excluded.generated_at""",
            (article_id, f"{article_id}.mp3", duration, config.tts_voice,
             config.tts_model, len(all_bytes), generated_at),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "Audio cached for article %d: %.1fs, %.1f KB",
        article_id, duration, len(all_bytes) / 1024,
    )


def get_audio_status(article_id: int, config: TiroConfig) -> dict:
    """Check whether cached audio exists for an article."""
    if not config.openai_api_key:
        return {"cached": False, "fallback": True}

    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT file_path, duration_seconds, voice, model, file_size_bytes, generated_at "
            "FROM audio WHERE article_id = ?",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"cached": False, "fallback": False}

    audio_path = config.library / "audio" / row["file_path"]
    if not audio_path.exists():
        logger.warning(
            "Audio record for article %d exists but file missing: %s",
            article_id, audio_path,
        )
        return {"cached": False, "fallback": False}

    return {
        "cached": True,
        "fallback": False,
        "duration_seconds": round(row["duration_seconds"], 1),
        "voice": row["voice"],
        "model": row["model"],
        "file_size_bytes": row["file_size_bytes"],
        "generated_at": row["generated_at"],
    }
