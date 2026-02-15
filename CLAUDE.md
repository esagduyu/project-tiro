# Project Tiro

## What This Is

Tiro is a local-first, open-source, model-agnostic reading OS for the AI age. It saves web pages and email newsletters as clean markdown, enriches them with AI-extracted metadata, and uses Claude Opus 4.6 for deep cross-document reasoning — daily digests, trust analysis, and learned reading preferences. Everything runs locally. The user owns their data.

Named after Cicero's freedman who preserved and organized his master's works for posterity.

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
uv sync                    # Install dependencies
uv run tiro init           # Initialize library (tiro-library/)
uv run python run.py       # Start server on localhost:8000
```

Before starting the server, kill any existing process on port 8000:
```bash
lsof -ti :8000 | xargs kill -9
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/ingest/url | Save a web page |
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

## Current Status

**Working on:** Checkpoint 15 — Chrome extension
**Completed:** Checkpoints 1–14

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
[ ] 15. Chrome extension
[ ] 16. Packaging
[ ] 17. Digest email
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
- **Browser cache busting**: Static files (CSS/JS) use `?v=N` query params in base.html and reader.html (currently v=18). Increment the version when modifying static files.
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
- **Inbox sort**: Sort dropdown (top right): Newest first (default), Oldest first, By importance. Auto-switches to "By importance" after classification runs. Importance order: must-read → summary-enough → discard → unclassified. VIP articles pin to top within each sort mode. Articles cached client-side for instant re-sorting.
- **Summary styling**: Summaries in both inbox and reader show as "**TL;DR** – *summary text*" (bold prefix, en dash, italicized body).
- **ai_tier in all queries**: The `ai_tier` column must be included in all SQL queries returning article data (articles list, detail, AND search) — same pattern as `source_type`.
- **Keyboard navigation** (Checkpoint 11): Full keyboard-first navigation. Inbox: `j`/`k` move selection, `Enter` opens article, `s` toggles VIP, `1`/`2`/`3` rate (dislike/like/love), `/` focuses search, `d` switches to digest, `a` switches to articles, `c` classify/reclassify, `g` go to stats, `?` shows shortcuts overlay. Digest view: `r` generates or regenerates digest. Reader: `b`/`Esc` goes back, `s` toggles VIP, `1`/`2`/`3` rate, `i` toggles analysis panel, `r` runs/re-runs analysis (when panel open), `g` go to stats, `?` shows shortcuts. Stats page: `b`/`Esc` back to inbox, `?` shows shortcuts. Keys are ignored when focus is on input/select elements. Selected article gets `.kb-selected` highlight class. Shortcuts overlay in `base.html` (shared), populated by JS per view. VIP star in reader view now clickable with `data-source-id`.
- **Content decay** (Checkpoint 12): `tiro/decay.py` recalculates `relevance_weight` for all articles. Liked/Loved articles immune (1.0). Others decay after 7-day grace period: default 0.95/day, disliked 0.90/day, VIP 0.98/day. Min weight 0.01. Runs on server startup (in `app.py` lifespan) and via `POST /api/decay/recalculate`. `GET /api/articles` supports `?include_decayed=false` (hides articles below threshold). Inbox defaults to hiding decayed articles, "Show archived" toggle to reveal them. Digest prompt includes `relevance_weight` for decay-aware ranking. Config values in `config.yaml` (`decay_rate_default`, `decay_rate_disliked`, `decay_rate_vip`, `decay_threshold`). **Gotcha**: "Show archived" also force-shows discarded articles, since an article can be both decayed and classified as discard — without this, archived+discarded articles stay hidden even after toggling.
- **Reading stats** (Checkpoint 13): `tiro/stats.py` provides `update_stat(config, field, increment)` and `get_stats(config, period)`. Stats updates hooked into `process_article()` (articles_saved), `mark_read()` (articles_read + reading_time), `rate_article()` (articles_rated). `GET /api/stats?period=week|month|all` returns daily_counts, totals, top_tags, top_sources (with love/like/dislike breakdowns), reading_streak. Stats page at `/stats` uses Chart.js (CDN) with 4 charts: saved bar, read-vs-saved line, top topics horizontal bar, sources engagement stacked bar. Summary cards show totals + streak. Nav link "Stats" in header. Charts stacked vertically (single-column). Love color is purple (#7c3aed) to distinguish from red dislike.
- **Export** (Checkpoint 14): `tiro/export.py` generates a zip bundle with `articles/*.md` files (frontmatter intact), `metadata.json` (articles, sources, tags, entities, relations, junction tables), and `README.md`. Filterable by tag, source_id, rating_min, date_from. `GET /api/export` streams the zip via `FileResponse` with `BackgroundTask` cleanup. `tiro export --output ./file.zip --tag ai` CLI command available. Export button on stats page header (keyboard shortcut `e`). `markdown_path` in DB stores just the filename — use `config.articles_dir / markdown_path` to resolve, NOT `config.library / markdown_path`.
- **Export** UI: Red button with white text on stats page. Clicking opens a confirmation dialog explaining what the zip contains (markdown files, metadata.json, README). Export only triggers after user clicks "Download". Dialog dismissible via Cancel, Esc, or clicking overlay.
- **Browser cache busting**: Currently at v=25 in base.html and reader.html. ALWAYS increment when modifying static files.
