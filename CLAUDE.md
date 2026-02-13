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

**Not yet implemented:** `tiro/mcp/` is an empty stub (checkpoint 9).

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

## Current Status

**Working on:** Checkpoint 8 — Email import
**Completed:** Checkpoints 1–7

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
[ ] 8. Email import works
[ ] 9. MCP server connects
[ ] 10. Learned preferences
[ ] 11. Keyboard navigation
[ ] 12. Content decay
[ ] 13. Reading stats
[ ] 14. Export works
[ ] 15. Chrome extension
[ ] 16. Packaging
[ ] 17. Digest email
-->

## Decisions & Notes

- **Subagents must clean up**: if a subagent starts uvicorn for testing, it must kill it before finishing
- **direnv**: user uses direnv for `ANTHROPIC_API_KEY`. Previously Claude Code subprocesses didn't inherit direnv env vars, but this has been fixed — API calls (Haiku extraction, Opus analysis/digest) now work from subagent-started servers.
- **readability-lxml strips images**: Sites using `<figure>/<picture>` wrappers (Substack, Medium, WordPress) lose all images through readability. Fixed by collecting `<figure>` images with text anchors from the original HTML, then re-injecting them at correct positions in readability's output.
- **readability-lxml vs table-layout sites**: Old sites like paulgraham.com use `<table>` for page layout. readability preserves the tables, and markdownify converts them to markdown table syntax, destroying the article structure. Fixed by stripping layout table tags (`table/tr/td/th`) before markdown conversion.
- **Author extraction**: readability-lxml doesn't extract authors. Added `<meta name="author">` and `<meta property="article:author">` parsing from raw HTML. Works for Substack, Medium, WordPress.
- **URL redirects**: Use final URL after redirects (via `response.url`) so Substack generic links (`substack.com/home/post/...`) resolve to the actual subdomain (`author.substack.com/p/...`), giving correct source names.
- **Reader view**: Uses marked.js (CDN) for client-side markdown rendering. Article content loaded via `GET /api/articles/{id}` which reads the markdown file via python-frontmatter.
- **Digest generation**: Opus 4.6 generates three digest variants (ranked, by_topic, by_entity) from article summaries + metadata. Prompt templates in `tiro/intelligence/prompts.py`. Cached in SQLite `digests` table by date+type. Opus call wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
- **Digest caching**: Cache lookup falls back to the most recent digest when today's doesn't exist yet (avoids regenerating at midnight). UI shows a time-ago banner ("Generated 3h ago") and turns yellow/amber when the digest is >24h stale, nudging the user to regenerate.
- **process_article() uses keyword-only args**: Call as `process_article(**extracted, config=config)`, not positional args.
- **Browser cache busting**: Static files (CSS/JS) use `?v=N` query params in base.html (currently v=10). Increment the version when modifying static files.
- **Opus JSON responses**: Opus may wrap JSON in ```json fences despite being told not to. Always strip markdown code fences before `json.loads()`. See `analysis.py` for the pattern.
- **Opus call duration**: Analysis calls can take up to a minute (full article text). Digest calls take 10-30s. UI loading text must reflect actual wait times.
- **Ingenuity analysis**: On-demand only (not precomputed). Cached in `articles.ingenuity_analysis` (JSON blob). `?refresh=true` to re-analyze. Prompt template in `prompts.py`, logic in `analysis.py`.
- **Semantic search**: `tiro/search/semantic.py` queries ChromaDB with `.query()`. ChromaDB returns cosine distances (0=identical, 2=opposite); convert to similarity with `1 - (distance / 2)`.
- **Related articles**: Auto-computed on ingest after ChromaDB add. Top 5 similar stored in `article_relations`. Haiku generates connection notes for top 3. `POST /api/recompute-relations` handles retroactive computation.
- **Search UI**: Debounced search bar in inbox, results display in same card format with similarity badge. Clear button reloads full inbox.
- **Clickable tags**: Tags in both inbox and reader are clickable. Inbox tags fill search bar and trigger search. Reader tags navigate to `/?q=tagname`. Inbox JS reads `?q=` URL param on load to support this.
- **Three-store consistency**: Articles exist in SQLite, ChromaDB, and as markdown files. Deleting an article requires cleaning all three plus junction tables (`article_tags`, `article_entities`, `article_relations`). ChromaDB orphans accumulate silently if not cleaned.
