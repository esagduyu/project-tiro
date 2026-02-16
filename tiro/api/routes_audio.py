"""Audio TTS API routes."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from tiro.tts import generate_article_audio, get_audio_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/articles", tags=["audio"])


@router.get("/{article_id}/audio/status")
async def audio_status(article_id: int, request: Request):
    """Check if cached audio exists for an article."""
    config = request.app.state.config
    status = get_audio_status(article_id, config)
    return {"success": True, "data": status}


@router.post("/{article_id}/audio/generate")
async def audio_generate(article_id: int, request: Request):
    """Generate TTS audio for an article (cached after first generation)."""
    config = request.app.state.config

    if not config.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API key not configured. Set openai_api_key in config.yaml or use Settings.",
        )

    # Check if already cached
    status = get_audio_status(article_id, config)
    if status.get("cached"):
        return {"success": True, "data": status}

    try:
        result = await asyncio.to_thread(generate_article_audio, article_id, config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("TTS generation failed for article %d: %s", article_id, e)
        raise HTTPException(status_code=502, detail=f"TTS generation failed: {e}")

    return {"success": True, "data": result}


@router.get("/{article_id}/audio")
async def audio_stream(article_id: int, request: Request):
    """Stream the cached MP3 file for an article."""
    config = request.app.state.config

    status = get_audio_status(article_id, config)
    if not status.get("cached"):
        raise HTTPException(status_code=404, detail="Audio not generated yet")

    file_path = config.library / "audio" / f"{article_id}.mp3"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=f"tiro-article-{article_id}.mp3",
    )
