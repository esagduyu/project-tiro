"""Text-to-speech generation for Tiro articles using OpenAI TTS API."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
import httpx

from tiro.config import TiroConfig
from tiro.database import get_connection

logger = logging.getLogger(__name__)


def chunk_text(text: str, max_chars: int = 4000) -> list[str]:
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
    """Remove markdown formatting to produce clean text for TTS.

    Strips images, converts links to their text, removes bold/italic markers,
    heading prefixes, code blocks, HTML tags, and horizontal rules. Collapses
    multiple blank lines.
    """
    # Remove code blocks (fenced)
    text = re.sub(r'```[\s\S]*?```', '', text)

    # Remove inline code
    text = re.sub(r'`([^`]*)`', r'\1', text)

    # Remove images: ![alt](url) -> alt (or nothing)
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)

    # Convert links: [text](url) -> text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)

    # Remove heading markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove bold/italic markers (order matters: *** before ** before *)
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

    # Remove list markers (unordered and ordered)
    text = re.sub(r'^\s*[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

    # Collapse multiple blank lines into two newlines (paragraph break)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def _estimate_mp3_duration(mp3_bytes: bytes) -> float:
    """Estimate MP3 duration from file size.

    OpenAI tts-1 outputs approximately 128kbps MP3, which is 16,000 bytes
    per second.
    """
    return len(mp3_bytes) / 16000.0


def _call_openai_tts(text: str, config: TiroConfig) -> bytes:
    """Call OpenAI TTS API and return MP3 bytes.

    Posts to https://api.openai.com/v1/audio/speech with the configured
    model, voice, and input text. Returns raw MP3 bytes.

    Raises:
        RuntimeError: If the API key is missing or the request fails.
    """
    if not config.openai_api_key:
        raise RuntimeError("openai_api_key not configured — cannot generate audio")

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {config.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.tts_model,
                "input": text,
                "voice": config.tts_voice,
                "response_format": "mp3",
            },
        )

    if response.status_code != 200:
        logger.error(
            "OpenAI TTS API error %d: %s", response.status_code, response.text[:500]
        )
        raise RuntimeError(
            f"OpenAI TTS API returned {response.status_code}: {response.text[:200]}"
        )

    return response.content


def generate_article_audio(
    article_id: int, config: TiroConfig
) -> dict:
    """Generate TTS audio for an article and cache it.

    Reads the article from SQLite and its markdown file, strips formatting,
    chunks the text, calls OpenAI TTS for each chunk, concatenates the MP3
    bytes, saves to disk, and records metadata in the audio table.

    Returns a dict with article_id, file_path, duration_seconds, voice,
    model, and file_size_bytes.

    Raises:
        ValueError: If the article is not found or its markdown file is missing.
        RuntimeError: If the OpenAI API key is not configured or the API fails.
    """
    # Load article metadata from SQLite
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT title, markdown_path FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Article {article_id} not found")
        title = row["title"]
        markdown_path = row["markdown_path"]
    finally:
        conn.close()

    # Load markdown content
    md_path = config.articles_dir / markdown_path
    if not md_path.exists():
        raise ValueError(f"Markdown file not found: {md_path}")

    post = frontmatter.load(str(md_path))
    content = post.content

    # Prepend title and strip markdown for clean speech text
    full_text = f"{title}\n\n{content}"
    speech_text = _strip_markdown_for_speech(full_text)

    # Chunk and generate audio for each chunk
    chunks = chunk_text(speech_text)
    if not chunks:
        raise ValueError(f"Article {article_id} produced no text chunks")

    logger.info(
        "Generating TTS audio for article %d (%d chunks, %d chars total)",
        article_id,
        len(chunks),
        sum(len(c) for c in chunks),
    )

    mp3_parts: list[bytes] = []
    for i, chunk in enumerate(chunks):
        logger.debug("TTS chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
        mp3_data = _call_openai_tts(chunk, config)
        mp3_parts.append(mp3_data)

    # Concatenate MP3 frames (independently decodable, so simple concat works)
    mp3_bytes = b"".join(mp3_parts)

    # Ensure audio directory exists and save file
    audio_dir = config.library / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{article_id}.mp3"
    audio_path.write_bytes(mp3_bytes)

    # Compute metadata
    duration = _estimate_mp3_duration(mp3_bytes)
    file_size = len(mp3_bytes)
    generated_at = datetime.now(timezone.utc).isoformat()

    # Store in the audio table (upsert — replace if regenerating)
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
            (
                article_id,
                f"{article_id}.mp3",
                duration,
                config.tts_voice,
                config.tts_model,
                file_size,
                generated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "Audio saved for article %d: %.1fs, %d bytes, %s",
        article_id,
        duration,
        file_size,
        audio_path,
    )

    return {
        "article_id": article_id,
        "file_path": f"{article_id}.mp3",
        "duration_seconds": round(duration, 1),
        "voice": config.tts_voice,
        "model": config.tts_model,
        "file_size_bytes": file_size,
    }


def get_audio_status(article_id: int, config: TiroConfig) -> dict:
    """Check whether cached audio exists for an article.

    Returns a dict with:
    - cached (bool): Whether audio has been generated and the file exists.
    - fallback (bool): True if openai_api_key is not configured (TTS unavailable).
    - duration_seconds, voice, model, generated_at: Present only when cached is True.
    """
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

    # Verify the file still exists on disk
    audio_path = config.library / "audio" / row["file_path"]
    if not audio_path.exists():
        # DB record exists but file is missing — treat as uncached
        logger.warning(
            "Audio record for article %d exists but file missing: %s",
            article_id,
            audio_path,
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
