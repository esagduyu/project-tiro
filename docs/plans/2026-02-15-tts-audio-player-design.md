# TTS Audio Player — Design Doc

**Date:** 2026-02-15
**Status:** Approved

## Summary

Add a text-to-speech player to the reader view that reads articles aloud. Uses OpenAI TTS API as the primary voice engine with browser `speechSynthesis` as a free fallback. Generated audio is cached locally as MP3 files to avoid repeated API costs.

## Architecture

### Backend

New `tiro/tts.py` module with three endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/articles/{id}/audio/status` | Check if cached audio exists |
| POST | `/api/articles/{id}/audio/generate` | Generate audio via OpenAI TTS, cache MP3 |
| GET | `/api/articles/{id}/audio` | Stream the cached MP3 file |

### Storage

- Directory: `{library}/audio/` alongside `{library}/articles/`
- One MP3 per article: `{article_id}.mp3`
- Metadata tracked in SQLite `audio` table (linked by article_id)

### Chunking

Articles are split at paragraph boundaries (`\n\n`), targeting ~4000 chars per chunk (OpenAI TTS limit is ~4096 chars). Each chunk is sent to the OpenAI `audio/speech` endpoint. Responses are concatenated into a single MP3 before caching.

### Fallback

If no `openai_api_key` is configured, the player uses the browser's `speechSynthesis` API directly. No backend call, no caching (since it's free and instant).

## Data Model

New `audio` table in SQLite:

```sql
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

- `article_id` is the primary key — one audio file per article
- `voice` and `model` stored to identify stale audio if settings change
- `duration_seconds` powers the player progress bar without loading the full file
- Article deletion must clean up the audio row + MP3 file (four-store consistency: SQLite, ChromaDB, markdown, audio)

## Frontend Player

Position: between `#reader-summary` and `#reader-body` in reader.html.

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Play/Pause  ━━━━ progress bar ━━━━  0:00 / 12:34  1x │
└─────────────────────────────────────────────────────┘
```

### Controls

- Play/Pause toggle
- Seekable progress bar (click to jump)
- Current time / total duration display
- Playback speed button (cycles: 1x -> 1.25x -> 1.5x -> 2x -> 1x)

### States

1. **Ready (not cached)** — "Generate audio" button
2. **Ready (cached)** — Full player bar, instant playback
3. **Generating** — Spinner + "Generating audio..." while backend works
4. **Playing** — Active player with all controls
5. **Fallback (no OpenAI key)** — Same player UI using `speechSynthesis`

### Keyboard

- `p` toggles play/pause in reader view
- Added to the `?` shortcuts overlay

### Implementation

- Uses `<audio>` element for OpenAI MP3 playback
- On page load, `GET /audio/status` determines initial state
- `speechSynthesis` fallback runs entirely client-side

## User Flows

### Play (not cached)

1. Page loads, `/audio/status` returns `{cached: false}`
2. Player shows "Generate audio" button
3. User clicks — frontend POSTs to `/audio/generate`, button shows spinner
4. Backend chunks article, calls OpenAI TTS per chunk, concatenates MP3
5. Backend saves to `{library}/audio/{id}.mp3`, inserts `audio` row
6. Returns success with duration — frontend GETs `/audio`, starts playback

### Play (cached)

1. Page loads, `/audio/status` returns `{cached: true, duration_seconds: 742}`
2. Player shows full bar with duration
3. User clicks play — frontend GETs `/audio`, instant playback

### Fallback (no OpenAI key)

1. `/audio/status` returns `{fallback: true}`
2. Player shows play button (no "Generate" step needed)
3. User clicks play — `speechSynthesis` reads article text directly

## Config & Setup

### New config fields

- `openai_api_key: str | None` — enables TTS (optional)
- `tts_voice: str = "nova"` — OpenAI voice (alloy, echo, fable, onyx, nova, shimmer)
- `tts_model: str = "tts-1"` — or `tts-1-hd` for higher quality at 2x cost

### `tiro init` flow

After Anthropic API key prompt:

```
Tiro can read articles aloud using OpenAI's text-to-speech.
Get your API key at https://platform.openai.com/api-keys

OpenAI API key (or press Enter to skip):
```

Same pattern: detect from env (`OPENAI_API_KEY`), show masked, confirm/replace/paste.

### Settings page

New "Text-to-Speech" section below Email Integration:
- Status card: configured/not configured, current voice
- Configure button -> modal with OpenAI key field, voice dropdown
- Saves to config.yaml, updates live config

### config.example.yaml

Document `openai_api_key`, `tts_voice`, `tts_model` with comments.

## Dependencies

- `openai` Python package (for TTS API calls)
- `pydub` or raw `io.BytesIO` concatenation for joining MP3 chunks (pydub needs ffmpeg; raw concatenation of MP3 frames is simpler and works without extra deps)

## Files to Create

| File | Purpose |
|------|---------|
| `tiro/tts.py` | TTS generation: chunking, OpenAI API calls, MP3 concatenation, caching |
| `tiro/api/routes_audio.py` | API endpoints for audio status, generate, stream |

## Files to Modify

| File | Changes |
|------|---------|
| `tiro/config.py` | Add `openai_api_key`, `tts_voice`, `tts_model` fields |
| `tiro/database.py` | Add `audio` table to schema |
| `tiro/app.py` | Register audio router, ensure `audio/` dir created in lifespan |
| `tiro/cli.py` | Add OpenAI key prompt to `tiro init` |
| `tiro/api/routes_settings.py` | Add TTS section to GET/POST settings |
| `tiro/frontend/templates/reader.html` | Add player div between summary and body |
| `tiro/frontend/static/reader.js` | Audio player logic, status check, playback controls |
| `tiro/frontend/templates/settings.html` | TTS config section + modal |
| `tiro/frontend/static/styles.css` | Player and TTS settings styles |
| `tiro/frontend/templates/base.html` | Bump cache version |
| `config.example.yaml` | Document TTS fields |
| `CLAUDE.md` | Update endpoints, checkpoint |
