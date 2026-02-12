# Project Tiro

## What This Is

Tiro is a local-first, open-source, model-agnostic reading OS for the AI age. It saves web pages and email newsletters as clean markdown, enriches them with AI-extracted metadata, and uses Claude Opus 4.6 for deep cross-document reasoning — daily digests, trust analysis, and learned reading preferences. Everything runs locally. The user owns their data.

Named after Cicero's freedman who preserved and organized his master's works for posterity.

**Context:** Built solo for the "Built with Opus 4.6: Claude Code Hackathon" (Feb 10–16, 2026). Must be fully open source, built from scratch. See SPEC.md for the full build plan.

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
- See SPEC.md § "Data Models" for the full SQLite schema, markdown format, and ChromaDB collection spec
- See SPEC.md § "Key Prompt Templates" for all Opus/Haiku prompt templates
- See SPEC.md § "API Endpoints" for the full endpoint list

## Current Status

**Working on:** Checkpoint 5 — Digest generates
**Next up:** Checkpoint 6 — Analysis works
**Completed:** Checkpoints 1–4 (skeleton runs, can save a URL, inbox shows articles, reader works)

<!-- UPDATE THIS SECTION AS YOU COMPLETE CHECKPOINTS -->
<!--
Checkpoint tracker:
[x] 1. Skeleton runs
[x] 2. Can save a URL
[x] 3. Inbox shows articles
[x] 4. Reader works
[ ] 5. Digest generates
[ ] 6. Analysis works
[ ] 7. Search + Related
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

- Use `uv` for all package management (not pip)
- hatchling needs explicit `[tool.hatch.build.targets.wheel] packages = ["tiro"]` since project name differs from package dir
- `uv run python run.py` to start the server
- **Before starting the server**, always kill any existing process on port 8000: `lsof -ti :8000 | xargs kill -9`
- **Subagents must clean up**: if a subagent starts uvicorn for testing, it must kill it before finishing
- **direnv**: user uses direnv for `ANTHROPIC_API_KEY`. Claude Code subprocesses don't inherit direnv env vars, so Haiku extraction fails silently in subagent-started servers. User must start the server from their own terminal for API calls to work.
- **readability-lxml strips images**: Sites using `<figure>/<picture>` wrappers (Substack, Medium, WordPress) lose all images through readability. Fixed by collecting `<figure>` images with text anchors from the original HTML, then re-injecting them at correct positions in readability's output.
- **readability-lxml vs table-layout sites**: Old sites like paulgraham.com use `<table>` for page layout. readability preserves the tables, and markdownify converts them to markdown table syntax, destroying the article structure. Fixed by stripping layout table tags (`table/tr/td/th`) before markdown conversion.
- **Author extraction**: readability-lxml doesn't extract authors. Added `<meta name="author">` and `<meta property="article:author">` parsing from raw HTML. Works for Substack, Medium, WordPress.
- **URL redirects**: Use final URL after redirects (via `response.url`) so Substack generic links (`substack.com/home/post/...`) resolve to the actual subdomain (`author.substack.com/p/...`), giving correct source names.
- **Reader view**: Uses marked.js (CDN) for client-side markdown rendering. Article content loaded via `GET /api/articles/{id}` which reads the markdown file via python-frontmatter.
