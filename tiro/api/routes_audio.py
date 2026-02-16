"""Audio TTS API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from tiro.tts import get_audio_status, stream_article_audio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/articles", tags=["audio"])


@router.get("/{article_id}/audio/status")
async def audio_status(article_id: int, request: Request):
    """Check if cached audio exists for an article."""
    config = request.app.state.config
    status = get_audio_status(article_id, config)
    return {"success": True, "data": status}


@router.get("/{article_id}/audio")
async def audio_stream(article_id: int, request: Request):
    """Stream audio for an article.

    If cached, serves the MP3 file directly. If not cached, streams from
    OpenAI TTS in real-time (browser starts playback within ~1-2s) and
    caches the result for future plays.
    """
    config = request.app.state.config

    # If cached, serve the file directly
    status = get_audio_status(article_id, config)
    if status.get("cached"):
        file_path = config.library / "audio" / f"{article_id}.mp3"
        return FileResponse(
            path=str(file_path),
            media_type="audio/mpeg",
            filename=f"tiro-article-{article_id}.mp3",
        )

    # Not cached — need OpenAI key
    if not config.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured.",
        )

    # Stream from OpenAI, cache when done
    try:
        return StreamingResponse(
            stream_article_audio(article_id, config),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'inline; filename="tiro-article-{article_id}.mp3"',
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
