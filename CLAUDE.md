# Project Tiro

## What This Is

Tiro is a local-first, open-source, model-agnostic reading OS for the AI age. It saves web pages and email newsletters as clean markdown, enriches them with AI-extracted metadata, and uses Claude Opus 4.6 for deep cross-document reasoning — daily digests, trust analysis, and learned reading preferences. Everything runs locally. The user owns their data.

Named after Cicero's freedman who preserved and organized his master's works for posterity. *"...without you the oracle was dumb." — Cicero to Tiro, 53 BC*

**Context:** Built solo for the "Built with Opus 4.6: Claude Code Hackathon" (Feb 10–16, 2026). Must be fully open source, built from scratch. See PROJECT_TIRO_SPEC.md for the full build plan.

## Architecture

```
Web UI (FastAPI serves HTML/JS at localhost:8000)
  ↕ REST API
FastAPI Backend (Python)
  ├── Ingestion Engine (readability-lxml + markdownify)
  ├── Intelligence Layer (Opus 4.6 — digests, analysis, preferences)
  ├── Lightweight Processing (Haiku — tags, entities, summaries)
  ├── Query Layer (ChromaDB semantic search + SQLite metadata)
  └── MCP Server (exposes knowledge base to Claude)
  ↕
Storage Layer (all local)
  ├── articles/*.md (markdown files with YAML frontmatter)
  ├── tiro.db (SQLite — metadata, preferences, stats)
  ├── chroma/ (ChromaDB — vector embeddings)
  └── config.yaml (user configuration)
```

**MCP server:** `tiro/mcp/server.py` exposes the library to Claude Desktop and Claude Code via 7 tools (see below).

## Tech Stack

- **Backend:** FastAPI, uvicorn, Python 3.11+
- **Content extraction:** readability-lxml, markdownify
- **Email parsing:** Python email stdlib → readability-lxml → markdownify
- **Storage:** SQLite (metadata), ChromaDB (vectors), markdown files on disk
- **Embeddings:** sentence-transformers (all-MiniLM-L6-v2) locally
- **AI (heavy):** Claude Opus 4.6 via Anthropic API (digests, analysis, preferences)
- **AI (light):** Claude Haiku 4.5 via Anthropic API (tags, entities, summaries)
- **Frontend:** Minimal HTML/CSS/JS served by FastAPI (Jinja2 templates)
- **MCP:** Python MCP SDK

## Key Conventions

- **Use `uv` for all Python version and dependency management** — never use pip directly. Use `uv pip install`, `uv venv`, `uv run`, etc. Dependencies defined in pyproject.toml.
- Python 3.11+, async throughout (async def for all route handlers)
- Use httpx for async HTTP calls
- Use python-frontmatter for reading/writing markdown with YAML frontmatter
- All files stored under a configurable `library_path` (default: `./tiro-library/`)
- Structured Anthropic API responses: always request JSON output, parse with error handling
- Logging via Python logging module, INFO level default
- Graceful error handling everywhere — never crash the server on bad input
- See PROJECT_TIRO_SPEC.md § "Data Models" for the full SQLite schema, markdown format, and ChromaDB collection spec
- See PROJECT_TIRO_SPEC.md § "Key Prompt Templates" for all Opus/Haiku prompt templates
- See PROJECT_TIRO_SPEC.md § "API Endpoints" for the full endpoint list

## Quick Start

```bash
uv sync                    # Install dependencies (creates venv automatically)
uv run tiro init           # Creates config.yaml, library, prompts for API key
uv run tiro run            # Start server on localhost:8000 (auto-opens browser)
uv run tiro run --lan      # Bind to 0.0.0.0 for LAN access (read on your phone)
```

Before starting the server, kill any existing process on port 8000:
```bash
lsof -ti :8000 | xargs kill -9
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/ingest/url | Save a web page |
| GET | /api/ingest/check?url=... | Check if URL is already saved (returns article data if found) |
| POST | /api/ingest/email | Save an uploaded .eml file |
| POST | /api/ingest/batch-email | Process all .eml files in a directory |
| GET | /api/articles | List articles (VIP pinned first) |
| GET | /api/articles/{id} | Get article with markdown content |
| PATCH | /api/articles/{id}/rate | Rate article (-1, 1, 2) |
| PATCH | /api/articles/{id}/read | Mark read, increment open count |
| GET | /api/sources | List sources with article counts |
| PATCH | /api/sources/{id}/vip | Toggle VIP status |
| GET | /api/articles/{id}/analysis | On-demand ingenuity/trust analysis |
| GET | /api/digest/today | Get/generate daily digest (all 3 variants) |
| GET | /api/digest/today/{type} | Get specific variant |
| GET | /api/search?q=... | Semantic search across articles |
| GET | /api/articles/{id}/related | Get related articles with connection notes |
| POST | /api/recompute-relations | Retroactively compute relations for all articles |
| POST | /api/classify | Classify unrated articles into tiers using Opus 4.6 |
| POST | /api/decay/recalculate | Recalculate content decay weights for all articles |
| GET | /api/stats?period=week\|month\|all | Reading stats (daily counts, top tags, top sources, streak) |
| GET | /api/export | Export library as zip (filterable: ?tag=, ?source_id=, ?rating_min=, ?date_from=) |
| POST | /api/digest/send | Send today's digest via email (requires digest_email in config) |
| POST | /api/ingest/imap | Check IMAP inbox for new newsletters and ingest them |
| GET | /api/settings/email | Get email config (passwords masked) |
| POST | /api/settings/email | Update email config (Gmail address, app password, features) |
| GET | /api/articles/{id}/audio/status | Check if TTS audio is cached |
| GET | /api/articles/{id}/audio | Stream or serve audio (generates + caches if not cached) |
| GET | /api/settings/tts | Get TTS config (key masked) |
| POST | /api/settings/tts | Update TTS config (OpenAI key, voice, model) |
| GET | /api/graph?min_articles=N | Knowledge graph nodes + edges |
| GET | /api/graph/node/{type}/{id}/articles | Articles linked to a graph node |
| GET | /api/filters | Filter facet counts (tiers, sources, tags, ratings, etc.) |
| GET | /api/settings/appearance | Get theme + page size config |
| POST | /api/settings/appearance | Update theme/page size |
| POST | /api/settings/theme/import | Import custom theme CSS |
| GET | /api/digest/history | List dates with cached digests (max 30) |
| GET | /api/digest/date/{date} | Get cached digest for specific date (404 if not found) |
| GET | /api/settings/digest-schedule | Get digest schedule config + email_configured flag |
| POST | /api/settings/digest-schedule | Update digest schedule (enabled, time, unread_only, tz_offset) |

## Current Status

**Completed:** 21 checkpoints + UX redesign (Checkpoint 22) + Digest scheduling & history

<!-- UPDATE THIS SECTION AS YOU COMPLETE CHECKPOINTS -->
<!--
Checkpoint tracker:
[x] 1. Skeleton runs
[x] 2. Can save a URL
[x] 3. Inbox shows articles
[x] 4. Reader works
[x] 5. Digest generates
[x] 6. Analysis works
[x] 7. Search + Related
[x] 8. Email import works
[x] 9. MCP server connects
[x] 10. Learned preferences
[x] 11. Keyboard navigation
[x] 12. Content decay
[x] 13. Reading stats
[x] 14. Export works
[x] 15. Chrome extension
[x] 16. Packaging
[x] 17. Digest email
[x] 18. Gmail IMAP + SMTP integration
[x] 19. TTS audio player
[x] 20. IMAP sync scheduler
[x] 21. Knowledge graph
-->

## Playwright MCP

Playwright MCP is configured at user scope. Use it to visually verify UI changes — navigate to pages, check chart rendering, test keyboard shortcuts, take screenshots.

**Testing workflow:**
1. Kill port 8000: `lsof -ti :8000 | xargs kill -9`
2. Start server: `uv run python run.py` (background)
3. Use `browser_navigate` to `localhost:8000`, then `browser_snapshot` / `browser_take_screenshot` / `browser_click` / `browser_evaluate` etc.
4. Kill server when done testing

**Last full test run:** 2026-02-15 — all Checkpoints 1–13 passed. See `docs/PLAYWRIGHT_TEST_NOTES.md` for detailed results, bugs found, and fixes applied.

**Tips from testing:**
- `browser_snapshot` is better than screenshots for interacting with elements (gives refs for clicking)
- `browser_evaluate` is useful for inspecting Chart.js instances, checking pixel data, or running `fetch()` against API endpoints
- `browser_console_messages` with `level: "error"` catches JS runtime errors
- Charts render on canvas — screenshots may appear blank if taken too early; use `browser_wait_for` with a 1-2s delay
- Full-page screenshots (`fullPage: true`) capture everything but canvas charts may need scrolling into view first

## Decisions & Notes

- **Subagents must clean up**: if a subagent starts uvicorn for testing, it must kill it before finishing
- **direnv**: user uses direnv for `ANTHROPIC_API_KEY`. Previously Claude Code subprocesses didn't inherit direnv env vars, but this has been fixed — API calls (Haiku extraction, Opus analysis/digest) now work from subagent-started servers.
- **readability-lxml strips images**: Sites using `<figure>/<picture>` wrappers (Substack, Medium, WordPress) lose all images through readability. Fixed by collecting `<figure>` images with text anchors from the original HTML, then re-injecting them at correct positions in readability's output.
- **readability-lxml vs table-layout sites**: Old sites like paulgraham.com use `<table>` for page layout. readability preserves the tables, and markdownify converts them to markdown table syntax, destroying the article structure. Fixed by stripping layout table tags (`table/tr/td/th`) before markdown conversion.
- **Author extraction**: readability-lxml doesn't extract authors. Added `<meta name="author">` and `<meta property="article:author">` parsing from raw HTML. Works for Substack, Medium, WordPress.
- **URL redirects**: Use final URL after redirects (via `response.url`) so Substack generic links (`substack.com/home/post/...`) resolve to the actual subdomain (`author.substack.com/p/...`), giving correct source names.
- **Reader view**: Uses marked.js (CDN) for client-side markdown rendering. Article content loaded via `GET /api/articles/{id}` which reads the markdown file via python-frontmatter.
- **Digest generation**: Opus 4.6 generates three digest variants (ranked, by_topic, by_entity) from article summaries + metadata. Prompt templates in `tiro/intelligence/prompts.py`. Cached in SQLite `digests` table by date+type. Opus call wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
- **Digest caching**: Cache lookup falls back to the most recent digest when today's doesn't exist yet (avoids regenerating at midnight). UI shows a time-ago banner ("Generated 3h ago") and turns yellow/amber when the digest is >24h stale, nudging the user to regenerate. `generate_digest()` must return a full datetime string for `created_at` (not just date), otherwise JS parses it as UTC midnight and the banner shows stale immediately.
- **process_article() uses keyword-only args**: Call as `process_article(**extracted, config=config)`, not positional args.
- **Browser cache busting**: Static files (CSS/JS) use `?v=N` query params in base.html (inherited by all templates). Increment the version when modifying static files.
- **Opus JSON responses**: Opus may wrap JSON in ```json fences despite being told not to. Always strip markdown code fences before `json.loads()`. See `analysis.py` for the pattern.
- **Opus call duration**: Analysis calls can take up to a minute (full article text). Digest calls take 10-30s. UI loading text must reflect actual wait times.
- **Ingenuity analysis**: On-demand only (not precomputed). Cached in `articles.ingenuity_analysis` (JSON blob with `analyzed_at` timestamp). `?refresh=true` to re-analyze, `?cache_only=true` to check cache without triggering Opus. Panel shows intro page first, user clicks "Run" to start. Results have collapsible dimension sections and aggregate-score-colored summary.
- **Semantic search**: `tiro/search/semantic.py` queries ChromaDB with `.query()`. ChromaDB returns cosine distances (0=identical, 2=opposite); convert to similarity with `1 - (distance / 2)`.
- **Related articles**: Auto-computed on ingest after ChromaDB add. Top 5 similar stored in `article_relations`. Haiku generates connection notes for top 3. `POST /api/recompute-relations` handles retroactive computation.
- **Search UI**: Debounced search bar in inbox, results display in same card format with similarity badge. Clear button reloads full inbox.
- **Clickable tags**: Tags in both inbox and reader are clickable. Inbox tags fill search bar and trigger search. Reader tags navigate to `/?q=tagname`. Inbox JS reads `?q=` URL param on load to support this.
- **Three-store consistency**: Articles exist in SQLite, ChromaDB, and as markdown files. Deleting an article requires cleaning all three plus junction tables (`article_tags`, `article_entities`, `article_relations`). ChromaDB orphans accumulate silently if not cleaned.
- **Email ingestion** (`tiro/ingestion/email.py`): Parses .eml files via Python `email` stdlib with `policy.default`. Handles multipart (prefers text/html over text/plain). Strips tracking pixels (1x1 images, Substack/Mailchimp tracking URLs) and UTM params from links. Runs HTML through readability + markdownify (same as web). Uses Subject as title, Date header as `published_at`, sender name/email for source creation. `process_article()` extended with optional `published_at` and `email_sender` kwargs.
- **Email duplicate detection**: Checked by title + email_sender (not URL, since emails have no URL). Sources created with `source_type = "email"` and `email_sender` column.
- **Email batch import**: `POST /api/ingest/batch-email` accepts `{"path": "/absolute/path"}` — tilde (`~`) is NOT expanded server-side, must use absolute paths or `$HOME`. CLI alternative: `python scripts/import_emails.py ./dir/` (works without server).
- **Source type pills**: Colored pill badges in inbox meta line — blue "saved" (web), pink "email", amber "rss". Clickable (triggers search). `source_type` must be included in all SQL queries that return article data (articles list, detail, search) or pills fall back to "saved".
- **MCP server** (`tiro/mcp/server.py`): FastMCP-based server on stdio transport. 7 tools: `search_articles`, `get_article`, `get_digest`, `get_articles_by_tag`, `get_articles_by_source`, `save_url`, `save_email`. Initializes its own config/SQLite/ChromaDB independently from FastAPI. `save_url` is `async def` — must `await fetch_and_extract()` (not `asyncio.run()`, which fails inside FastMCP's already-running event loop). `process_article` wrapped in `asyncio.to_thread()`. Runnable via `tiro-mcp` CLI entry point or `python -m tiro.mcp.server`. Config for Claude Desktop/Code documented in README.
- **MCP + ANTHROPIC_API_KEY**: Claude Desktop spawns the MCP server as a child process — direnv env vars are NOT inherited. Must pass `ANTHROPIC_API_KEY` explicitly in the `"env"` block of `claude_desktop_config.json`, otherwise Haiku extraction silently returns empty (no tags, no summary).
- **HTML comment crash**: `_collect_content_images()` in `web.py` iterates container children — lxml includes `HtmlComment` nodes whose `.tag` is not a string. Must skip non-element nodes with `if not isinstance(child.tag, str): continue`.
- **Substack UUID URLs**: URLs like `derekthompson.org/p/568334c2-...` are JS-rendered pages with no article content in static HTML. Only `/p/slug-name` format URLs work for Substack ingestion.
- **Learned preferences**: `tiro/intelligence/preferences.py` uses Opus 4.6 to classify unrated articles into `must-read`, `summary-enough`, or `discard` tiers based on user ratings. Requires at least 5 rated articles. Unrated articles capped at 50. Prompt template in `prompts.py`. Results stored in `articles.ai_tier` column.
- **Tier-based inbox UI**: Must-read articles get green left border + "Must Read" badge. Summary-enough articles get indigo left border + "Summary" badge with full summary visible. Discard articles hidden by default with "Show discarded" toggle. "Classify inbox" button always visible — shows count when unclassified exist, switches to "Reclassify" (muted outline style) when all classified. Disabled when fewer than 5 articles are rated. `POST /api/classify` accepts `{refresh: true}` to clear all tiers and reclassify.
- **Inbox sort**: Sort dropdown (top right): Unread first (default), Newest first, Oldest first, By importance. Auto-switches to "By importance" after classification runs. "Unread first" puts unread articles on top, then VIP, then newest. "Newest/Oldest first" sort purely by date with VIP as tiebreaker only (not pinned to top). "By importance" sorts must-read → summary-enough → discard → unclassified. VIP is always a second-order priority within each sort mode, never the primary sort key. Articles cached client-side for instant re-sorting.
- **Summary styling**: Summaries in both inbox and reader show as "**TL;DR** – *summary text*" (bold prefix, en dash, italicized body).
- **ai_tier in all queries**: The `ai_tier` column must be included in all SQL queries returning article data (articles list, detail, AND search) — same pattern as `source_type`.
- **Keyboard navigation** (Checkpoint 11+): Full keyboard-first navigation. Inbox: `j`/`k` move selection, `Enter` opens article, `s` toggles VIP, `1`/`2`/`3` rate (dislike/like/love), `/` focuses search, `d` switches to digest, `f` toggles filter panel, `a` switches to articles, `c` classify/reclassify, `g` go to stats, `v` go to graph, `?` shows shortcuts overlay. Digest view: `r` generates or regenerates digest. Reader: `b`/`Esc` goes back, `s` toggles VIP, `1`/`2`/`3` rate, `p` play/pause audio, `i` toggles analysis panel, `r` runs/re-runs analysis (when panel open), `d` go to digest, `g` go to stats, `v` go to graph, `?` shows shortcuts. Stats page: `b`/`Esc` back to inbox, `e` export, `v` go to graph, `?` shortcuts. Settings page: `b`/`Esc` back, `v` go to graph, `?` shortcuts. Graph page: `b`/`Esc` back, `?` shortcuts. Keys are ignored when focus is on input/select elements. Selected article gets `.kb-selected` highlight class. Shortcuts overlay in `base.html` (shared), populated by JS per view.
- **Content decay** (Checkpoint 12): `tiro/decay.py` recalculates `relevance_weight` for all articles. Liked/Loved articles immune (1.0). Others decay after 7-day grace period: default 0.95/day, disliked 0.90/day, VIP 0.98/day. Min weight 0.01. Runs on server startup (in `app.py` lifespan) and via `POST /api/decay/recalculate`. `GET /api/articles` supports `?include_decayed=false` (hides articles below threshold). Inbox defaults to hiding decayed articles, "Show archived" toggle to reveal them. Digest prompt includes `relevance_weight` for decay-aware ranking. Config values in `config.yaml` (`decay_rate_default`, `decay_rate_disliked`, `decay_rate_vip`, `decay_threshold`). **Gotcha**: "Show archived" also force-shows discarded articles, since an article can be both decayed and classified as discard — without this, archived+discarded articles stay hidden even after toggling.
- **Reading stats** (Checkpoint 13): `tiro/stats.py` provides `update_stat(config, field, increment)` and `get_stats(config, period)`. Stats updates hooked into `process_article()` (articles_saved), `mark_read()` (articles_read + reading_time), `rate_article()` (articles_rated). `GET /api/stats?period=week|month|all` returns daily_counts, totals, top_tags, top_sources (with love/like/dislike breakdowns), reading_streak. Stats page at `/stats` uses Chart.js (CDN) with 4 charts: saved bar, read-vs-saved line, top topics horizontal bar, sources engagement stacked bar. Summary cards show totals + streak. Nav link "Stats" in header. Charts stacked vertically (single-column). Love color is purple (#7c3aed) to distinguish from red dislike.
- **Export** (Checkpoint 14): `tiro/export.py` generates a zip bundle with `articles/*.md` files (frontmatter intact), `metadata.json` (articles, sources, tags, entities, relations, junction tables), and `README.md`. Filterable by tag, source_id, rating_min, date_from. `GET /api/export` streams the zip via `FileResponse` with `BackgroundTask` cleanup. `tiro export --output ./file.zip --tag ai` CLI command available. Export button on stats page header (keyboard shortcut `e`). `markdown_path` in DB stores just the filename — use `config.articles_dir / markdown_path` to resolve, NOT `config.library / markdown_path`.
- **Chrome extension** (Checkpoint 15): `extension/` directory with Manifest V3. Popup shows current page title/URL, "Save to Tiro" button, optional VIP toggle. POSTs to `localhost:8000/api/ingest/url`. Shows success with article title + source + "Open in Tiro" link, or error if server not running. Icons: blue circle with white "T" (16/48/128px, generated with Pillow). `process_article()` now returns `source_id` in its response dict so VIP toggle works. Load as unpacked extension via `chrome://extensions`. On popup open, checks `GET /api/ingest/check?url=...` — if already saved, shows "Already in your library" with title, time-ago, and link. `POST /api/ingest/url` 409 duplicate response now returns structured JSON (`{error: "already_saved", data: {id, title, source, ingested_at}}`) instead of plain HTTPException detail string.
- **Packaging** (Checkpoint 16): pyproject.toml has full metadata (author, classifiers, URLs), MIT LICENSE file, comprehensive README with features/architecture/CLI/extension/MCP/keyboard docs. CLI enhanced: `tiro init` auto-generates `config.yaml` from `config.example.yaml` template, detects existing `ANTHROPIC_API_KEY` from env (shows masked, lets user confirm/replace/paste new), saves chosen key to root `config.yaml`. `load_config()` reads `anthropic_api_key` from config.yaml and sets env var if not already set. `tiro run` auto-opens browser (use `--no-browser` to skip). `tiro import-emails ./dir/` for bulk .eml import. `config.yaml` is gitignored (contains user's API key); `config.example.yaml` is shipped with commented API key options. Fresh install flow: `uv sync` → `uv run tiro init` → `uv run tiro run` (no manual file copying).
- **Export** UI: Red button with white text on stats page. Clicking opens a confirmation dialog explaining what the zip contains (markdown files, metadata.json, README). Export only triggers after user clicks "Download". Dialog dismissible via Cancel, Esc, or clicking overlay.
- **Digest email** (Checkpoint 17): `tiro/intelligence/email_digest.py` converts markdown digest to HTML email and sends via SMTP. `POST /api/digest/send` triggers manually. Config: `digest_email`, `smtp_host` (default localhost), `smtp_port` (default 1025). Uses `smtplib`. HTML email has inline styles, absolute article links (`http://host:port/articles/N`), Tiro-branded header/footer. For dev/demo, run mailhog: `docker run -p 1025:1025 -p 8025:8025 mailhog/mailhog`. Returns 400 if no `digest_email` configured, 503 if SMTP connection refused.
- **Published date display**: Inbox, sorting, and related articles all use `published_at || ingested_at` so email articles show their original send date, not ingestion date. Backend SQL sort uses `COALESCE(published_at, ingested_at)`.
- **Gmail IMAP + SMTP integration** (Checkpoint 18): Bidirectional email integration. SMTP: `send_digest_email()` supports STARTTLS + login when `smtp_user`/`smtp_password` configured (Gmail App Password); falls back to plain SMTP (mailhog) without credentials. IMAP: `tiro/ingestion/imap.py` with `check_imap_inbox(config)` connects via `IMAP4_SSL`, fetches UNSEEN from configured label, passes raw bytes to existing `parse_eml()` → `process_article()`, marks processed as Seen, leaves failed as Unseen for retry. Duplicates detected by title+sender (same as email ingestion). CLI: `tiro setup-email` (interactive Gmail setup — address, app password, features, label), `tiro check-email` (trigger IMAP check). `tiro init` offers email setup after API key. API: `POST /api/ingest/imap` (trigger IMAP check), `GET /api/settings/email` (read config, passwords masked), `POST /api/settings/email` (update config.yaml + live config). Settings page at `/settings`: status cards (Send Digests / Receive Newsletters with green dot), action buttons (Check email now, Send test digest), Configure Email modal with form. Toast notifications for feedback. Keyboard: `b`/`Esc` back, `?` shortcuts. Nav link added to header (Settings + Stats). Config fields: `smtp_user`, `smtp_password`, `smtp_use_tls`, `imap_host`, `imap_port`, `imap_user`, `imap_password`, `imap_label`, `imap_enabled`, `imap_sync_interval`.
- **TTS audio player** (Checkpoint 19): `tiro/tts.py` with `stream_article_audio()` async generator that streams MP3 bytes from OpenAI TTS API via `httpx.AsyncClient.stream()`. Chunks articles at paragraph boundaries (~4000 chars, OpenAI limit is ~4096). For each chunk, streams response bytes directly to the browser AND accumulates them in a buffer. After all chunks streamed, caches complete MP3 to `{library}/audio/{id}.mp3` and records metadata in SQLite `audio` table (article_id PK, file_path, duration_seconds, voice, model, file_size_bytes, generated_at). `GET /api/articles/{id}/audio` is a smart endpoint: serves cached FileResponse if exists, otherwise returns StreamingResponse from OpenAI. `GET /api/articles/{id}/audio/status` returns `{cached, fallback, duration_seconds}`. Frontend player bar between summary and body in reader.html — play/pause button shows spinner while buffering (uses `playing` event, not `play`, to detect actual audio output), seekable progress bar, speed control (1x/1.25x/1.5x/2x), time display. During streaming playback, only elapsed time shown (total duration unknown); on cached playback, both shown. `speechSynthesis` fallback when no OpenAI key — includes progress bar via `onboundary` charIndex, speed control (cancels+restarts at current position with new rate), estimated duration from word count (~150 wpm). Config: `openai_api_key`, `tts_voice` (default "nova"), `tts_model` (default "tts-1"). Available voices: alloy, echo, fable, onyx, nova, shimmer. Available models: tts-1 (fast, $15/1M chars), tts-1-hd (higher quality, $30/1M chars). Settings page TTS section with status card, configure modal (key + voice dropdown + model dropdown). `tiro init` prompts for OpenAI key after Anthropic key + email setup. Keyboard: `p` toggles play/pause. Four-store consistency: article deletion must clean up audio row + MP3 file. **Gotcha**: `get_audio_status()` must use `config.library / "audio" / row["file_path"]` (not `config.library / row["file_path"]`) — file_path in DB is just the filename (e.g. "8.mp3"), not a relative path including the audio/ directory.
- **IMAP sync scheduler** (Checkpoint 20): `asyncio` background task in FastAPI lifespan polls IMAP inbox every N minutes via `check_imap_inbox()`. Config: `imap_sync_interval: int = 15` (minutes, 0 = manual only). Defaults to 15 everywhere — TiroConfig, CLI setup, Settings POST model, and modal prefill. The background loop reads `config.imap_sync_interval` each cycle so Settings page changes take effect on the next cycle without server restart. Setting interval to 0 stops the loop. Task created in lifespan if `imap_enabled` and `imap_sync_interval > 0`, cancelled on shutdown. Logs results at INFO (if messages found) or DEBUG (no messages). Settings page email section shows "Auto-sync every N min" or "Manual only" in the IMAP status card. Configure email modal has an "Auto-sync interval" dropdown (Manual / 5 / 10 / 15 / 30 / 60 min). Label and interval fields hide/show when Receive checkbox is toggled.
- **Knowledge graph** (Checkpoint 21): `tiro/api/routes_graph.py` computes nodes (entities + tags) and edges (article co-occurrence) from existing junction tables. `GET /api/graph?min_articles=N` returns `{nodes, edges}` — builds article_id→node_id mapping, counts co-occurrences via pairwise iteration, filters by min_articles threshold. `GET /api/graph/node/{type}/{id}/articles` returns articles for a node. Frontend at `/graph` uses d3.js v7 force simulation with SVG. Node colors: blue (person), green (company), orange (org), grey (tag). Node radius scales with `sqrt(count)`. Labels shown for count>=4. Edges: strokeWidth from `log(weight)`, opacity from weight. Interactions: hover tooltip, click node → bottom panel with article list, drag nodes, zoom/pan. Min-articles slider (1-5, default 2) re-fetches and re-renders. Inline `<style>` in graph.html (self-contained). Keyboard: `v` navigates to graph (from inbox, reader, stats, settings), `b`/`Esc` back, `?` shortcuts.
- **UX Redesign (Checkpoint 22):** Major overhaul across 8 phases (16 tasks). Theme system: `tiro/frontend/static/themes/papyrus.css` (light) + `roman-night.css` (dark) with 20 `--tiro-*` CSS variables each. Roman color palette: papyrus cream `#FAF6F0` bg, terra cotta `#C45B3E` accent, olive `#6B7F4E` secondary, warm gold `#B8943E` for links/VIP. Dark: warm charcoal `#1C1A17` bg. Sidebar nav: 220px left sidebar with icons+labels, unread badge, dark mode toggle, About Tiro link, mobile hamburger menu. Routing: Digest extracted to `/digest`, inbox at `/inbox`, `/` redirects to `/inbox`. API: `GET /api/articles` rewritten with full filtering (`ai_tier`, `source_id`, `tag`, `rating`, `is_read`, `is_vip`, `date_from`/`date_to`, `ingestion_method`, `q` search) + offset/limit pagination. `GET /api/filters` returns facet counts. `GET/POST /api/settings/appearance` for theme + page size. `POST /api/settings/theme/import` for custom themes. Filter panel: right-edge peeking tab (CSS `writing-mode: vertical-rl`, `position: fixed`), opens 320px slide-out panel with 11 filter sections (tiers, ratings, sources, tags, read status, VIP, ingestion method, date range). Active filter pills above article list. Tab shows accent dot when filters active. Panel uses sibling selector `.filter-panel.open + .filter-tab` for open state styling. `ingestion_method` column added to articles table with backfill from URL presence. MCP: `search_articles` tool enhanced with all filter params, new `list_filters` tool. Settings Appearance section: light/dark theme dropdowns, page size, custom theme upload. Responsive: sidebar collapses to icons at 1200px, hamburger menu at 768px, filter panel full-width on mobile. Full plan in `docs/plans/2026-02-16-ux-redesign-plan.md`. Phase 2 additions: hi-res 128px Tironian et logo (`logo-128.png`, Apple Symbols font, Pillow-generated), distinct color systems for tier badges (`--tiro-tier-must-read: #B5334D` crimson, `--tiro-tier-summary: #4A6FA5` lapis blue) vs source pills (`--tiro-source-web: #7B7168`, `--tiro-source-email: #8B6B8A`, `--tiro-source-rss: #B8943E`), VIP-only toggle filter in inbox toolbar (client-side filter from `cachedArticles`), page titles use Tironian et (⁊) instead of em dash, Cicero quote footer on every page ("...without you the oracle was dumb." — Cicero to Tiro, 53 BC).
- **LAN access** (`--lan` flag): `tiro run --lan` binds uvicorn to `0.0.0.0` instead of `127.0.0.1`, making Tiro accessible from other devices on the local network. Prints the machine's LAN IP on startup. Can also set `host: "0.0.0.0"` in config.yaml permanently. No authentication yet — see PROJECT_TIRO_SPEC.md Future Roadmap for planned auth, mDNS discovery, HTTPS, and daemon mode.
- **Digest scheduling & history**: Background scheduler generates + emails digests at a configurable daily time. Config: `digest_schedule_enabled`, `digest_schedule_time` (HH:MM), `digest_unread_only`, `digest_timezone_offset` (from JS `getTimezoneOffset()`). Scheduler uses `_compute_sleep_until()` to compute seconds until target time in user's timezone via stored UTC offset, then `asyncio.sleep()`. Auto-emails all 3 sections (by_topic → by_entity → ranked) if SMTP configured; deduplicates by tracking `last_email_date`. `send_digest_email()` accepts `all_sections: bool = False` — when True, fetches all 3 digest types and combines them with section headings. Settings API at `GET/POST /api/settings/digest-schedule` — POST dynamically starts/stops scheduler via `app.state.digest_task`. History API: `GET /api/digest/history` returns dates with cached digests (grouped from SQLite), `GET /api/digest/date/{date}` returns specific date's digest (exact match, no fallback). `generate_digest()` accepts `unread_only: bool = False`, passed through to `_gather_articles()` which adds `WHERE a.is_read = 0`. Frontend: digest.html has history `<select>` dropdown (populated from `/api/digest/history`, skips today), Schedule button (clock icon, `.active` class when enabled), schedule modal (enable checkbox, time input, unread-only checkbox, email status indicator). History select change loads via `loadHistoricalDigest()`. Digest generation refreshes history dropdown. Schedule button shows accent color when active.
- **Browser cache busting**: Currently at v=46 in base.html. ALWAYS increment when modifying static files.
