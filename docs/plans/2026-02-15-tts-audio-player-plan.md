# TTS Audio Player Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a text-to-speech audio player to the reader view that reads articles aloud using OpenAI TTS with local MP3 caching, falling back to browser speechSynthesis.

**Architecture:** Backend `tiro/tts.py` handles chunking articles at paragraph boundaries (~4000 chars), calling OpenAI TTS API via httpx, concatenating MP3 chunks, and caching to `{library}/audio/`. SQLite `audio` table links cached files to articles. Frontend player bar sits between the AI summary and article body in reader.html. `speechSynthesis` fallback when no OpenAI key is configured.

**Tech Stack:** httpx (already a dependency) for OpenAI TTS API calls, `<audio>` element for MP3 playback, Web Speech API for fallback.

---

### Task 1: Config fields + database schema

**Files:**
- Modify: `tiro/config.py` — add 3 fields to TiroConfig
- Modify: `tiro/database.py` — add `audio` table to SCHEMA

**Step 1: Add config fields**

In `tiro/config.py`, add after the `imap_enabled` field in the TiroConfig dataclass:

```python
    openai_api_key: str | None = None
    tts_voice: str = "nova"
    tts_model: str = "tts-1"
```

Also in `load_config()`, after the existing `ANTHROPIC_API_KEY` env var block, add:

```python
    # Set OPENAI_API_KEY env var from config if not already set
    if config.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = config.openai_api_key
```

**Step 2: Add audio table to database schema**

In `tiro/database.py`, add to the end of the `SCHEMA` string (before the closing `"""`):

```sql
-- Audio cache (TTS-generated MP3 files linked to articles)
CREATE TABLE IF NOT EXISTS audio (
    article_id INTEGER PRIMARY KEY REFERENCES articles(id),
    file_path TEXT NOT NULL,
    duration_seconds REAL,
    voice TEXT NOT NULL,
    model TEXT NOT NULL,
    file_size_bytes INTEGER,
    generated_at TEXT NOT NULL
);
```

**Step 3: Commit**

```bash
git add tiro/config.py tiro/database.py
git commit -m "Add TTS config fields and audio table schema"
```

---

### Task 2: TTS backend module

**Files:**
- Create: `tiro/tts.py`

This is the core TTS module. It handles:
1. Splitting article text into chunks at paragraph boundaries
2. Calling OpenAI TTS API for each chunk via httpx
3. Concatenating MP3 chunks into a single file
4. Caching to disk and recording in SQLite

**Step 1: Create `tiro/tts.py`**

```python
"""Text-to-speech generation for Tiro articles."""

import io
import logging
import struct
from datetime import datetime
from pathlib import Path

import httpx

from tiro.config import TiroConfig
from tiro.database import get_connection

logger = logging.getLogger(__name__)

# OpenAI TTS has a ~4096 character input limit
MAX_CHUNK_CHARS = 4000


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split text into chunks at paragraph boundaries, each under max_chars."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If a single paragraph exceeds max, split at sentence boundaries
        if len(para) > max_chars:
            sentences = para.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(current) + len(sentence) + 2 > max_chars and current:
                    chunks.append(current.strip())
                    current = ""
                current += sentence + " "
            continue

        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = ""
        current += para + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _call_openai_tts(text: str, config: TiroConfig) -> bytes:
    """Call OpenAI TTS API and return MP3 bytes."""
    api_key = config.openai_api_key
    if not api_key:
        raise ValueError("No openai_api_key configured")

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.tts_model,
                "input": text,
                "voice": config.tts_voice,
                "response_format": "mp3",
            },
        )
        response.raise_for_status()
        return response.content


def _estimate_mp3_duration(mp3_bytes: bytes) -> float:
    """Estimate MP3 duration from file size (rough: ~16 kB/s for tts-1 output)."""
    # OpenAI tts-1 outputs ~128kbps MP3, so ~16000 bytes per second
    return len(mp3_bytes) / 16000.0


def generate_article_audio(article_id: int, config: TiroConfig) -> dict:
    """Generate TTS audio for an article and cache it.

    Returns dict with: article_id, file_path, duration_seconds, voice, model.
    """
    # Get article content from database
    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT title, markdown_path FROM articles WHERE id = ?",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise ValueError(f"Article {article_id} not found")

    # Read the markdown file content
    md_path = config.articles_dir / row["markdown_path"]
    if not md_path.exists():
        raise ValueError(f"Markdown file not found: {md_path}")

    import frontmatter
    post = frontmatter.load(str(md_path))
    content = post.content

    # Prepend title for the audio
    full_text = f"{row['title']}.\n\n{content}"

    # Strip markdown formatting for cleaner TTS
    clean_text = _strip_markdown_for_speech(full_text)

    # Chunk and generate
    chunks = chunk_text(clean_text)
    if not chunks:
        raise ValueError("No text content to generate audio from")

    logger.info(
        "Generating TTS for article %d: %d chunks, %d chars total",
        article_id, len(chunks), sum(len(c) for c in chunks),
    )

    mp3_parts = []
    for i, chunk in enumerate(chunks):
        logger.info("  Chunk %d/%d (%d chars)...", i + 1, len(chunks), len(chunk))
        mp3_data = _call_openai_tts(chunk, config)
        mp3_parts.append(mp3_data)

    # Concatenate MP3 chunks (MP3 frames are independently decodable)
    full_mp3 = b"".join(mp3_parts)

    # Save to disk
    audio_dir = config.library / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{article_id}.mp3"
    file_path = audio_dir / filename
    file_path.write_bytes(full_mp3)

    duration = _estimate_mp3_duration(full_mp3)
    generated_at = datetime.now().isoformat()

    # Record in database
    conn = get_connection(config.db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO audio
               (article_id, file_path, duration_seconds, voice, model, file_size_bytes, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (article_id, filename, duration, config.tts_voice, config.tts_model,
             len(full_mp3), generated_at),
        )
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "Audio cached for article %d: %s (%.1fs, %.1f KB)",
        article_id, filename, duration, len(full_mp3) / 1024,
    )

    return {
        "article_id": article_id,
        "file_path": filename,
        "duration_seconds": round(duration, 1),
        "voice": config.tts_voice,
        "model": config.tts_model,
        "file_size_bytes": len(full_mp3),
    }


def get_audio_status(article_id: int, config: TiroConfig) -> dict:
    """Check if audio is cached for an article."""
    if not config.openai_api_key:
        return {"cached": False, "fallback": True}

    conn = get_connection(config.db_path)
    try:
        row = conn.execute(
            "SELECT file_path, duration_seconds, voice, model, generated_at "
            "FROM audio WHERE article_id = ?",
            (article_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return {"cached": False, "fallback": False}

    # Verify file still exists
    file_path = config.library / "audio" / row["file_path"]
    if not file_path.exists():
        return {"cached": False, "fallback": False}

    return {
        "cached": True,
        "fallback": False,
        "duration_seconds": row["duration_seconds"],
        "voice": row["voice"],
        "model": row["model"],
        "generated_at": row["generated_at"],
    }


def _strip_markdown_for_speech(text: str) -> str:
    """Remove markdown formatting that sounds bad when read aloud."""
    import re
    # Remove markdown images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"\1", text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove heading markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    # Remove code blocks (fenced)
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
```

**Step 2: Commit**

```bash
git add tiro/tts.py
git commit -m "Add TTS module with OpenAI chunked generation and caching"
```

---

### Task 3: Audio API routes

**Files:**
- Create: `tiro/api/routes_audio.py`
- Modify: `tiro/app.py` — register router, create audio dir in lifespan

**Step 1: Create `tiro/api/routes_audio.py`**

```python
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
```

**Step 2: Register in app.py**

In `tiro/app.py`, add the import alongside other routers:

```python
    from tiro.api.routes_audio import router as audio_router
```

And add after the other `app.include_router()` calls:

```python
    app.include_router(audio_router)
```

In the `lifespan` function, add after `config.articles_dir.mkdir(...)`:

```python
    # Ensure audio directory exists
    (config.library / "audio").mkdir(parents=True, exist_ok=True)
```

**Step 3: Commit**

```bash
git add tiro/api/routes_audio.py tiro/app.py
git commit -m "Add audio API routes (status, generate, stream)"
```

---

### Task 4: Frontend player HTML + CSS

**Files:**
- Modify: `tiro/frontend/templates/reader.html` — add player div
- Modify: `tiro/frontend/static/styles.css` — player styles
- Modify: `tiro/frontend/templates/base.html` — bump cache version

**Step 1: Add player div to reader.html**

In `reader.html`, add between `reader-summary` and `reader-body` (after line 39, before line 40):

```html
        <div id="audio-player" class="audio-player" style="display: none;">
            <div id="audio-generate" class="audio-generate">
                <button id="audio-generate-btn" class="audio-generate-btn">Listen to this article</button>
            </div>
            <div id="audio-generating" class="audio-generating" style="display: none;">
                <div class="audio-spinner"></div>
                <span>Generating audio...</span>
            </div>
            <div id="audio-controls" class="audio-controls" style="display: none;">
                <button id="audio-play-btn" class="audio-play-btn" title="Play/Pause">&#9654;</button>
                <div class="audio-progress-wrap">
                    <div id="audio-progress" class="audio-progress">
                        <div id="audio-progress-fill" class="audio-progress-fill"></div>
                    </div>
                </div>
                <span id="audio-time" class="audio-time">0:00 / 0:00</span>
                <button id="audio-speed-btn" class="audio-speed-btn" title="Playback speed">1x</button>
            </div>
            <audio id="audio-el"></audio>
        </div>
```

**Step 2: Add player CSS to styles.css**

Append to the end of `styles.css` (before the final `@media` block):

```css
/* --- Audio player --- */

.audio-player {
    background: #f8f9fb;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 2rem;
}

.audio-generate {
    text-align: center;
}

.audio-generate-btn {
    padding: 0.5rem 1.25rem;
    border: 1px solid var(--accent);
    border-radius: 6px;
    background: var(--accent);
    color: white;
    font-size: 0.85rem;
    font-family: inherit;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
}

.audio-generate-btn:hover {
    background: var(--accent-hover);
}

.audio-generating {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    color: var(--muted);
    font-size: 0.85rem;
}

.audio-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}

.audio-controls {
    display: flex;
    align-items: center;
    gap: 0.6rem;
}

.audio-play-btn {
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 50%;
    background: var(--accent);
    color: white;
    font-size: 0.8rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: background 0.15s;
}

.audio-play-btn:hover {
    background: var(--accent-hover);
}

.audio-progress-wrap {
    flex: 1;
    cursor: pointer;
}

.audio-progress {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    position: relative;
    overflow: hidden;
}

.audio-progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    width: 0%;
    transition: width 0.1s linear;
}

.audio-time {
    font-size: 0.75rem;
    color: var(--muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    min-width: 85px;
    text-align: center;
}

.audio-speed-btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: none;
    font-size: 0.75rem;
    font-family: inherit;
    font-weight: 600;
    color: var(--muted);
    cursor: pointer;
    transition: all 0.15s;
    flex-shrink: 0;
}

.audio-speed-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
}

/* Fallback mode styling */
.audio-generate-btn.audio-fallback-btn {
    background: none;
    color: var(--fg-secondary);
    border-color: var(--border);
}

.audio-generate-btn.audio-fallback-btn:hover {
    background: var(--card-hover);
    border-color: var(--fg-secondary);
}
```

**Step 3: Bump cache version**

In `base.html`, change `v=27` to `v=28` for both CSS and JS. In `reader.html`, change `v=27` to `v=28` for `reader.js`.

**Step 4: Commit**

```bash
git add tiro/frontend/templates/reader.html tiro/frontend/static/styles.css tiro/frontend/templates/base.html
git commit -m "Add audio player HTML and CSS to reader view"
```

---

### Task 5: Frontend player JavaScript

**Files:**
- Modify: `tiro/frontend/static/reader.js` — add audio player logic + keyboard shortcut
- Modify: `tiro/frontend/static/app.js` — add `p` to READER_SHORTCUTS

**Step 1: Add audio player logic to reader.js**

Add a new function `setupAudioPlayer(articleId, articleContent)` and call it from `loadArticle()` after the summary is rendered (after the `// Markdown body` section, around line 115), passing the article content:

```javascript
        // Audio player
        setupAudioPlayer(a.id, a.content || "");
```

Then add the full `setupAudioPlayer` function at the bottom of `reader.js` (before `setupReaderKeyboard`):

```javascript
/* --- Audio Player --- */

let audioState = { fallback: false, playing: false, speechUtterance: null };

async function setupAudioPlayer(articleId, articleContent) {
    const player = document.getElementById("audio-player");
    if (!player) return;

    // Check audio status
    try {
        const res = await fetch(`/api/articles/${articleId}/audio/status`);
        const json = await res.json();
        if (!json.success) return;

        const data = json.data;
        player.style.display = "";

        if (data.fallback) {
            // No OpenAI key — use speechSynthesis fallback
            audioState.fallback = true;
            setupFallbackPlayer(articleContent);
        } else if (data.cached) {
            // Audio already generated — show player
            showAudioControls(articleId, data.duration_seconds);
        } else {
            // Not cached — show generate button
            setupGenerateButton(articleId);
        }
    } catch (err) {
        console.error("Audio status check failed:", err);
    }
}

function setupGenerateButton(articleId) {
    const genDiv = document.getElementById("audio-generate");
    const genBtn = document.getElementById("audio-generate-btn");

    genDiv.style.display = "";

    genBtn.addEventListener("click", async () => {
        genDiv.style.display = "none";
        document.getElementById("audio-generating").style.display = "flex";

        try {
            const res = await fetch(`/api/articles/${articleId}/audio/generate`, {
                method: "POST",
            });
            const json = await res.json();

            if (!res.ok || !json.success) {
                throw new Error(json.detail || "Generation failed");
            }

            document.getElementById("audio-generating").style.display = "none";
            showAudioControls(articleId, json.data.duration_seconds);
        } catch (err) {
            console.error("Audio generation failed:", err);
            document.getElementById("audio-generating").style.display = "none";
            genDiv.style.display = "";
            genBtn.textContent = "Generation failed — retry";
        }
    });
}

function showAudioControls(articleId, durationSeconds) {
    document.getElementById("audio-generate").style.display = "none";
    document.getElementById("audio-generating").style.display = "none";
    const controls = document.getElementById("audio-controls");
    controls.style.display = "flex";

    const audio = document.getElementById("audio-el");
    const playBtn = document.getElementById("audio-play-btn");
    const progressWrap = document.querySelector(".audio-progress-wrap");
    const progressFill = document.getElementById("audio-progress-fill");
    const timeEl = document.getElementById("audio-time");
    const speedBtn = document.getElementById("audio-speed-btn");

    audio.src = `/api/articles/${articleId}/audio`;

    // Show estimated duration before metadata loads
    if (durationSeconds) {
        timeEl.textContent = `0:00 / ${formatAudioTime(durationSeconds)}`;
    }

    // Update duration when metadata loads
    audio.addEventListener("loadedmetadata", () => {
        timeEl.textContent = `0:00 / ${formatAudioTime(audio.duration)}`;
    });

    // Play/pause
    playBtn.addEventListener("click", toggleAudioPlayback);

    audio.addEventListener("play", () => {
        playBtn.innerHTML = "&#9646;&#9646;";
        audioState.playing = true;
    });
    audio.addEventListener("pause", () => {
        playBtn.innerHTML = "&#9654;";
        audioState.playing = false;
    });
    audio.addEventListener("ended", () => {
        playBtn.innerHTML = "&#9654;";
        audioState.playing = false;
        progressFill.style.width = "0%";
    });

    // Progress bar
    audio.addEventListener("timeupdate", () => {
        if (audio.duration) {
            const pct = (audio.currentTime / audio.duration) * 100;
            progressFill.style.width = pct + "%";
            timeEl.textContent =
                formatAudioTime(audio.currentTime) + " / " + formatAudioTime(audio.duration);
        }
    });

    // Seek
    progressWrap.addEventListener("click", (e) => {
        if (!audio.duration) return;
        const rect = progressWrap.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        audio.currentTime = pct * audio.duration;
    });

    // Speed
    const speeds = [1, 1.25, 1.5, 2];
    let speedIndex = 0;
    speedBtn.addEventListener("click", () => {
        speedIndex = (speedIndex + 1) % speeds.length;
        audio.playbackRate = speeds[speedIndex];
        speedBtn.textContent = speeds[speedIndex] + "x";
    });
}

function toggleAudioPlayback() {
    if (audioState.fallback) {
        toggleFallbackPlayback();
        return;
    }

    const audio = document.getElementById("audio-el");
    if (!audio || !audio.src) return;

    if (audio.paused) {
        audio.play();
    } else {
        audio.pause();
    }
}

/* --- speechSynthesis fallback --- */

function setupFallbackPlayer(articleContent) {
    if (!window.speechSynthesis) return;

    const genDiv = document.getElementById("audio-generate");
    const genBtn = document.getElementById("audio-generate-btn");

    genDiv.style.display = "";
    genBtn.textContent = "Listen (browser voice)";
    genBtn.classList.add("audio-fallback-btn");

    genBtn.addEventListener("click", () => {
        genDiv.style.display = "none";
        const controls = document.getElementById("audio-controls");
        controls.style.display = "flex";

        // Hide progress and speed for fallback (speechSynthesis has limited control)
        document.querySelector(".audio-progress-wrap").style.display = "none";
        document.getElementById("audio-speed-btn").style.display = "none";
        document.getElementById("audio-time").textContent = "";

        startFallbackSpeech(articleContent);
    });
}

function startFallbackSpeech(text) {
    // Strip markdown for speech
    const clean = text
        .replace(/!\[[^\]]*\]\([^\)]+\)/g, "")
        .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1")
        .replace(/\*{1,3}([^*]+)\*{1,3}/g, "$1")
        .replace(/#{1,6}\s+/g, "")
        .replace(/`[^`]+`/g, "")
        .replace(/<[^>]+>/g, "")
        .trim();

    const utterance = new SpeechSynthesisUtterance(clean);
    audioState.speechUtterance = utterance;
    audioState.playing = true;

    const playBtn = document.getElementById("audio-play-btn");
    playBtn.innerHTML = "&#9646;&#9646;";

    utterance.onend = () => {
        playBtn.innerHTML = "&#9654;";
        audioState.playing = false;
    };

    speechSynthesis.speak(utterance);
}

function toggleFallbackPlayback() {
    if (!window.speechSynthesis) return;

    const playBtn = document.getElementById("audio-play-btn");

    if (speechSynthesis.speaking && !speechSynthesis.paused) {
        speechSynthesis.pause();
        playBtn.innerHTML = "&#9654;";
        audioState.playing = false;
    } else if (speechSynthesis.paused) {
        speechSynthesis.resume();
        playBtn.innerHTML = "&#9646;&#9646;";
        audioState.playing = true;
    }
}

function formatAudioTime(seconds) {
    if (!seconds || !isFinite(seconds)) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
}
```

**Step 2: Add `p` keyboard shortcut to reader**

In `reader.js`, in the `setupReaderKeyboard` switch statement (around line 486), add a new case before `case "g"`:

```javascript
            case "p":
                e.preventDefault();
                toggleAudioPlayback();
                break;
```

**Step 3: Add `p` to shortcuts overlay**

In `tiro/frontend/static/app.js`, find `READER_SHORTCUTS` and add after the `{ keys: ["r"], desc: "Run / re-run analysis (panel open)" }` line:

```javascript
    { keys: ["p"], desc: "Play / pause audio" },
```

**Step 4: Commit**

```bash
git add tiro/frontend/static/reader.js tiro/frontend/static/app.js
git commit -m "Add audio player JavaScript with OpenAI TTS and speechSynthesis fallback"
```

---

### Task 6: CLI + Settings page TTS config

**Files:**
- Modify: `tiro/cli.py` — add OpenAI key prompt to `cmd_init`
- Modify: `tiro/api/routes_settings.py` — add TTS settings endpoints
- Modify: `tiro/frontend/templates/settings.html` — add TTS section + modal

**Step 1: Add OpenAI key prompt to `tiro init`**

In `tiro/cli.py`, in `cmd_init()`, after the email setup section (after the `_interactive_email_setup` call) and before the final print statements, add:

```python
    # Offer OpenAI TTS setup
    print()
    print("Tiro can read articles aloud using OpenAI's text-to-speech.")
    print("Get your API key at https://platform.openai.com/api-keys")
    print()

    openai_key = ""
    existing_openai = os.environ.get("OPENAI_API_KEY", "") or (yaml.safe_load(root_config.read_text()) or {}).get("openai_api_key", "")
    if existing_openai:
        masked = existing_openai[:7] + "..." + existing_openai[-4:]
        print(f"Found existing OpenAI key: {masked}")
        choice = input("Use this key? [Y/n] or paste a different one: ").strip()
        if choice == "" or choice.lower() in ("y", "yes"):
            openai_key = existing_openai
        elif choice.lower() in ("n", "no"):
            openai_key = input("OpenAI API key (or press Enter to skip): ").strip()
        else:
            openai_key = choice
    else:
        openai_key = input("OpenAI API key (or press Enter to skip): ").strip()

    if openai_key:
        config_data = yaml.safe_load(root_config.read_text()) or {}
        config_data["openai_api_key"] = openai_key
        root_config.write_text(yaml.dump(config_data, default_flow_style=False))
        print(f"OpenAI key saved to {root_config}")
    else:
        print("Skipped — articles will use browser voice (free, lower quality).")
```

**Step 2: Add TTS settings to routes_settings.py**

Add a GET and POST for TTS settings. Add to the existing `get_email_settings`:

```python
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
```

Add `import os` to the top of `routes_settings.py`.

**Step 3: Add TTS section to settings.html**

In `settings.html`, add a new section after the Email Integration section (after `</div>` for `settings-configure`). Add the TTS status section, configure button, and a TTS modal (following same patterns as email).

The TTS section should include:
- Status card showing configured/not, voice name
- "Configure TTS" button opening a modal with: OpenAI key input, voice dropdown (alloy/echo/fable/onyx/nova/shimmer), model dropdown (tts-1/tts-1-hd)
- Toast notifications reusing existing `showToast()` function

The JS for this section follows the exact same pattern as the email config modal — load status on init, render status card, modal for configuration, POST to save.

**Step 4: Commit**

```bash
git add tiro/cli.py tiro/api/routes_settings.py tiro/frontend/templates/settings.html
git commit -m "Add TTS config to CLI init, settings API, and settings page"
```

---

### Task 7: config.example.yaml + CLAUDE.md + final polish

**Files:**
- Modify: `config.example.yaml` — document TTS fields
- Modify: `CLAUDE.md` — update endpoints table, add checkpoint

**Step 1: Update config.example.yaml**

Add after the IMAP section:

```yaml
# Text-to-Speech (optional)
# Tiro can read articles aloud using OpenAI's TTS API.
# Get your key at https://platform.openai.com/api-keys
# openai_api_key: "sk-..."
# tts_voice: "nova"     # Options: alloy, echo, fable, onyx, nova, shimmer
# tts_model: "tts-1"    # Options: tts-1 (fast), tts-1-hd (higher quality, 2x cost)
```

**Step 2: Update CLAUDE.md**

Add to the API endpoints table:
```
| GET | /api/articles/{id}/audio/status | Check if TTS audio is cached |
| POST | /api/articles/{id}/audio/generate | Generate TTS audio via OpenAI (cached) |
| GET | /api/articles/{id}/audio | Stream cached MP3 file |
```

Add to the API GET/POST settings rows:
```
| GET | /api/settings/tts | Get TTS config (key masked) |
| POST | /api/settings/tts | Update TTS config (OpenAI key, voice, model) |
```

Update checkpoint tracker and status. Bump cache version note to v=28.

**Step 3: Commit**

```bash
git add config.example.yaml CLAUDE.md
git commit -m "Document TTS config and update checkpoint tracker"
```

---

### Task 8: Test end-to-end with Playwright

**Testing checklist:**

1. Start server: `lsof -ti :8000 | xargs kill -9; uv run python run.py &`
2. Navigate to a reader page — verify audio player div appears
3. Without OpenAI key: verify "Listen (browser voice)" fallback button appears
4. Configure OpenAI key via Settings page TTS modal
5. Navigate to reader — verify "Listen to this article" button appears
6. Click generate — verify spinner, then player controls appear
7. Verify play/pause, progress bar, speed control work
8. Navigate away and back — verify cached audio plays instantly (no generate step)
9. Press `p` — verify play/pause toggles
10. Press `?` — verify shortcuts overlay includes `p` shortcut
11. Check `/api/articles/{id}/audio/status` returns `{cached: true, duration_seconds: ...}`
12. Kill server when done

**No automated tests** — this project doesn't have a test suite. Manual verification via Playwright.
