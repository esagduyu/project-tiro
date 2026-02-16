<p align="center">
  <img src="tiro/frontend/static/logo-128.png" alt="Tiro" width="80" height="80">
</p>

<h1 align="center">Tiro</h1>

<p align="center"><strong>A local-first reading OS for the AI age.</strong></p>

<p align="center"><em>"...without you the oracle was dumb."</em><br><small>— Cicero to Tiro, 53 BC</small></p>

---

Tiro saves web pages and email newsletters as clean markdown on your machine, enriches them with AI-extracted tags, entities, and summaries, and uses Claude Opus 4.6 for deep cross-document reasoning — daily digests that find contradictions between sources, trust analysis on demand, and learned reading preferences that adapt to you.

Named after [Cicero's freedman](https://www.gutenberg.org/files/21200/21200-h/21200-h.htm) who preserved and organized his master's works for posterity, Tiro does the same for your digital knowledge.

*Built solo for the [Built with Opus 4.6: a Claude Code Hackathon](https://cerebralvalley.ai/e/claude-code-hackathon) (Feb 10–16, 2026) — a week-long virtual hackathon by Anthropic and Cerebral Valley celebrating one year of Claude Code.*

---

## Why Tiro?

- **Local-first** — Your data lives on your machine as plain markdown files, SQLite, and ChromaDB. No cloud, no lock-in.
- **Model-agnostic data layer** — Content stored in open formats, portable and usable with any AI.
- **Opinionated intelligence** — Opus 4.6 generates ranked digests, clusters articles by topic and entity, and flags bias and unsourced claims.
- **Minimal friction** — One command to run, clean distraction-free reader UI, full keyboard navigation.
- **Own your context** — One-click export of your entire library as portable markdown + JSON.

---

## Quick Start

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/), [Anthropic API key](https://console.anthropic.com/), optionally [OpenAI API key](https://platform.openai.com/api-keys) for TTS

```bash
git clone https://github.com/esagduyu/project-tiro.git
cd project-tiro
uv sync                       # creates venv + installs all dependencies
uv run tiro init              # creates config, library, prompts for API key
uv run tiro run               # starts server at localhost:8000, opens browser
```

That's it. Save your first article by pasting a URL into the inbox.

> **Tip:** If you use `direnv`, set `ANTHROPIC_API_KEY` in your `.envrc` instead of adding it to config.yaml.
>
> **Note:** All `tiro` commands should be run with `uv run tiro` so they execute inside the project's virtual environment.

---

## Features

### Ingestion

- **Save web pages** — Paste a URL, get a clean markdown article with extracted metadata
- **Import emails** — Drag .eml files or bulk import a directory of newsletters
- **Chrome extension** — One-click save from any browser tab (see [Chrome Extension](#chrome-extension) below)
- **Auto-enrichment** — Haiku extracts tags, named entities, and a 2-3 sentence summary on every save

### Intelligence (Opus 4.6)

- **Daily digest** — Three digest variants: ranked by importance, grouped by topic, grouped by entity. Opus finds contradictions between sources, connects threads, and surfaces insights you'd miss.
- **Ingenuity analysis** — On-demand bias detection, factual confidence scoring, and novelty assessment for any article. Only runs when you ask (saves tokens).
- **Learned preferences** — Rate a few articles, and Opus classifies the rest into must-read / summary-enough / discard tiers based on your demonstrated taste.

### Reading

- **Clean reader** — Distraction-free article view with full markdown rendering
- **Listen to articles** — OpenAI TTS reads articles aloud with streaming playback (starts in ~2s), cached as MP3. Falls back to browser speech synthesis when no OpenAI key is configured.
- **Semantic search** — Find articles by meaning, not just keywords
- **Related articles** — Auto-computed on save with AI-generated connection notes
- **Knowledge graph** — Interactive d3.js force-directed graph showing entities and tags connected by article co-occurrence. Density slider, click-to-explore article panel.
- **Content decay** — Unengaged articles naturally fade from digests over time

### Interface

- **Sidebar navigation** — Persistent left sidebar with Inbox, Digest, Graph, Stats, Settings. Collapses to icons on narrower screens, hamburger menu on mobile.
- **Filter panel** — Right-edge tab opens a slide-out panel with 11 filter facets: AI tier, rating, source, tag, read status, VIP, ingestion method, date range. Active filter pills. URL-synced state.
- **Dark mode** — Toggle between Papyrus (warm cream) and Roman Night (warm charcoal) themes. Persists via localStorage.
- **Theming** — CSS variable-based theme system with 20 `--tiro-*` variables. Roman-inspired palette: terra cotta accent, olive secondary, warm gold for links. Custom theme import support.
- **Pagination** — Configurable page size (10/25/50), server-side offset/limit pagination with keyboard-friendly navigation.

### Productivity

- **Keyboard-first** — Full `j`/`k`/`Enter`/`Esc` navigation, ratings with `1`/`2`/`3`, `f` for filter panel, shortcuts overlay with `?`
- **Gmail integration** — Send digest emails via Gmail SMTP, auto-ingest newsletters via IMAP label monitoring with configurable auto-sync (every 5–60 min)
- **Settings page** — Configure email, IMAP sync schedule, TTS, appearance (themes + page size) from the web UI
- **Reading stats** — Charts showing articles saved/read, top topics, source engagement, reading streak
- **Export** — Download your entire library as a portable zip (markdown files + metadata JSON)
- **MCP server** — Query your library from Claude Desktop or Claude Code

---

## Architecture

```
Web UI (localhost:8000 — sidebar nav, dark mode, filter panel, themes)
  ↕ REST API
FastAPI Backend
  ├── Ingestion Engine (readability-lxml + markdownify + IMAP)
  ├── Intelligence Layer (Opus 4.6 — digests, analysis, preferences)
  ├── Lightweight Processing (Haiku — tags, entities, summaries)
  ├── TTS Engine (OpenAI TTS streaming + speechSynthesis fallback)
  ├── Query Layer (ChromaDB semantic search + SQLite metadata)
  ├── Knowledge Graph (d3.js force-directed visualization)
  └── MCP Server (7 tools for Claude integration)
  ↕
Storage Layer (all local)
  ├── articles/*.md      (markdown files with YAML frontmatter)
  ├── audio/*.mp3        (cached TTS audio files)
  ├── tiro.db            (SQLite — metadata, preferences, stats, audio)
  ├── chroma/            (ChromaDB — vector embeddings)
  └── config.yaml
```

**Tech stack:** FastAPI, SQLite, ChromaDB, sentence-transformers, readability-lxml, markdownify, Anthropic API (Opus 4.6 + Haiku 4.5), OpenAI TTS API

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `uv run tiro init` | Initialize library, create databases, prompt for API keys + email setup |
| `uv run tiro run` | Start server at localhost:8000 and open browser |
| `uv run tiro run --no-browser` | Start server without opening browser |
| `uv run tiro export -o backup.zip` | Export library as zip (supports `--tag`, `--source-id`, `--rating-min`, `--date-from` filters) |
| `uv run tiro import-emails ./newsletters/` | Bulk import .eml files from a directory |
| `uv run tiro setup-email` | Configure Gmail SMTP + IMAP integration |
| `uv run tiro check-email` | Check IMAP inbox for new newsletters |
| `uv run tiro-mcp` | Start the MCP server (for Claude Desktop/Code integration) |

---

## Chrome Extension

A minimal "Save to Tiro" Chrome extension lives in the `extension/` directory.

### Features

- Shows the current page title and URL before saving
- Detects if the URL is already saved — shows "Already in your library" with a link
- Optional VIP toggle to mark the source as a favorite
- Success confirmation with article title, source, and "Open in Tiro" link
- Error state if the Tiro server isn't running

### Installation

1. Open `chrome://extensions` in Chrome (or any Chromium-based browser)
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `extension/` directory from this repo
5. The Tiro icon (blue circle with white "T") appears in your toolbar

> The Tiro server must be running at `localhost:8000` for the extension to work.

---

## MCP Server — Connect Tiro to Claude

Tiro includes an MCP (Model Context Protocol) server that exposes your reading library to Claude Desktop and Claude Code.

### Available Tools

| Tool | Description |
|------|-------------|
| `search_articles(query, ...)` | Semantic search with optional filters (ai_tier, source_id, tag, rating, date range, etc.) |
| `get_article(article_id)` | Full article content and metadata |
| `get_digest(digest_type)` | Today's daily digest (ranked, by_topic, by_entity) |
| `get_articles_by_tag(tag)` | Articles filtered by topic tag |
| `get_articles_by_source(source)` | Articles filtered by source name or domain |
| `list_filters()` | Available filter facets with counts (tiers, sources, tags, ratings) |
| `save_url(url)` | Save a web page to your library |
| `save_email(file_path)` | Save an .eml newsletter to your library |

### Claude Code

Add to your project's `.mcp.json` (or `~/.claude/settings.json` under `mcpServers`):

```json
{
  "mcpServers": {
    "tiro": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/project-tiro", "tiro-mcp"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-..."
      }
    }
  }
}
```

### Claude Desktop

Add to your Claude Desktop config file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tiro": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/project-tiro", "tiro-mcp"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-..."
      }
    }
  }
}
```

Replace `/path/to/project-tiro` with the actual path to your clone, and add your Anthropic API key.

---

## Export

Export your entire library (or a filtered subset) as a portable zip bundle:

```bash
uv run tiro export --output my-library.zip
uv run tiro export --output ai-articles.zip --tag ai
uv run tiro export --output favorites.zip --rating-min 1
```

The zip contains:
- `articles/` — All markdown files with YAML frontmatter intact
- `metadata.json` — Full structured data (articles, sources, tags, entities, relations)
- `README.md` — Bundle format documentation

Also available via the API (`GET /api/export`) and the Export button on the Stats page.

---

## Keyboard Shortcuts

### Inbox

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up through articles |
| `Enter` | Open selected article |
| `s` | Toggle VIP on selected article's source |
| `1` / `2` / `3` | Rate: dislike / like / love |
| `/` | Focus search bar |
| `f` | Toggle filter panel |
| `d` | Go to digest |
| `a` | Switch to articles view |
| `c` | Classify / reclassify inbox |
| `g` | Go to stats |
| `v` | Go to knowledge graph |
| `?` | Show shortcuts overlay |

### Reader

| Key | Action |
|-----|--------|
| `b` / `Esc` | Back to inbox |
| `s` | Toggle VIP |
| `1` / `2` / `3` | Rate: dislike / like / love |
| `p` | Play / pause audio |
| `i` | Toggle analysis panel |
| `r` | Run / re-run analysis (when panel open) |
| `d` | Go to digest |
| `g` | Go to stats |
| `v` | Go to knowledge graph |
| `?` | Show shortcuts overlay |

### Stats

| Key | Action |
|-----|--------|
| `b` / `Esc` | Back to inbox |
| `e` | Export library |
| `v` | Go to knowledge graph |
| `?` | Show shortcuts overlay |

### Graph

| Key | Action |
|-----|--------|
| `b` / `Esc` | Back to inbox |
| `?` | Show shortcuts overlay |

### Settings

| Key | Action |
|-----|--------|
| `b` / `Esc` | Back to inbox |
| `v` | Go to knowledge graph |
| `?` | Show shortcuts overlay |

---

## Project Structure

```
project-tiro/
├── tiro/                       # Python package
│   ├── app.py                  # FastAPI app, router registration
│   ├── cli.py                  # CLI commands (init, run, export, import-emails, setup-email, check-email)
│   ├── config.py               # Config loading (dataclass + YAML)
│   ├── database.py             # SQLite schema and helpers
│   ├── vectorstore.py          # ChromaDB initialization
│   ├── decay.py                # Content decay system
│   ├── stats.py                # Reading stats tracking
│   ├── export.py               # Library export (zip generation)
│   ├── tts.py                  # OpenAI TTS streaming + caching
│   ├── api/                    # FastAPI route handlers
│   ├── ingestion/              # Web + email content extraction
│   ├── intelligence/           # Opus 4.6 features (digest, analysis, preferences)
│   ├── search/                 # Semantic search + related articles
│   ├── mcp/                    # MCP server for Claude integration
│   └── frontend/               # HTML templates, CSS, JS, themes
├── extension/                  # Chrome extension
├── scripts/                    # Utility scripts
├── pyproject.toml              # Package config
└── tiro-library/               # Default data directory (gitignored)
```

---

## License

MIT

---

<p align="center"><em>"...without you the oracle was dumb."</em><br><small>— Cicero to Tiro, 53 BC</small></p>
