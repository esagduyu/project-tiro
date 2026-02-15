# Tiro

**A local-first reading OS for the AI age.**

Tiro saves web pages and email newsletters as clean markdown on your machine, enriches them with AI-extracted tags, entities, and summaries, and uses Claude Opus 4.6 for deep cross-document reasoning — daily digests that find contradictions between sources, trust analysis on demand, and learned reading preferences that adapt to you.

Named after Cicero's freedman who preserved and organized his master's works for posterity, Tiro does the same for your digital knowledge.

*Built solo for the [Built with Opus 4.6: a Claude Code Hackathon](https://cerebralvalley.ai/e/claude-code-hackathon) (Feb 10–16, 2026) — a week-long virtual hackathon by Anthropic and Cerebral Valley celebrating one year of Claude Code.*

## Why Tiro?

- **Local-first** — Your data lives on your machine as plain markdown files, SQLite, and ChromaDB. No cloud, no lock-in.
- **Model-agnostic data layer** — Content stored in open formats, portable and usable with any AI.
- **Opinionated intelligence** — Opus 4.6 generates ranked digests, clusters articles by topic and entity, and flags bias and unsourced claims.
- **Minimal friction** — One command to run, clean distraction-free reader UI.

## Quick Start

```bash
git clone https://github.com/esagduyu/project-tiro.git
cd project-tiro
uv pip install -e .
tiro init        # creates library directory, initializes databases
tiro run         # starts server at localhost:8000
```

Requires Python 3.11+ and an [Anthropic API key](https://console.anthropic.com/).

## How It Works

```
Save a URL or email → Extract content (readability + markdownify)
  → AI extracts tags, entities, summary (Haiku)
  → Store markdown file + SQLite metadata + vector embedding
  → Opus 4.6 generates daily digests, trust analysis, and preference learning
```

## MCP Server — Connect Tiro to Claude

Tiro includes an MCP (Model Context Protocol) server that exposes your reading library to Claude Desktop and Claude Code. This lets you ask Claude questions like "What articles do I have about AI regulation?" or "Save this URL to my reading library" directly from your AI assistant.

### Available Tools

| Tool | Description |
|------|-------------|
| `search_articles(query)` | Semantic search across your library |
| `get_article(article_id)` | Full article content and metadata |
| `get_digest(digest_type)` | Today's daily digest (ranked, by_topic, by_entity) |
| `get_articles_by_tag(tag)` | Articles filtered by topic tag |
| `get_articles_by_source(source)` | Articles filtered by source name or domain |
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

### Standalone

You can also run the MCP server directly for testing:

```bash
uv run tiro-mcp
# or
uv run python -m tiro.mcp.server
```

## Chrome Extension

A minimal "Save to Tiro" Chrome extension lives in the `extension/` directory. It adds a toolbar button that saves the current page to your local Tiro library with one click.

### Features

- Shows the current page title and URL before saving
- Optional VIP toggle to mark the source as a favorite
- Detects if the URL is already saved — shows "Already in your library" with a link to the article
- Success confirmation with article title, source, and "Open in Tiro" link
- Error state if the Tiro server isn't running

### Installation

1. Open `chrome://extensions` in Chrome (or any Chromium-based browser)
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `extension/` directory from this repo
5. The Tiro icon (blue circle with white "T") appears in your toolbar

> The Tiro server must be running at `localhost:8000` for the extension to work.

## Export

Export your entire library (or a filtered subset) as a portable zip bundle:

```bash
# Full library
tiro export --output my-library.zip

# Filtered
tiro export --output ai-articles.zip --tag ai
tiro export --output favorites.zip --rating-min 1
tiro export --output recent.zip --date-from 2026-02-01
```

The zip contains:
- `articles/` — All markdown files with YAML frontmatter intact
- `metadata.json` — Full structured data (articles, sources, tags, entities, relations)
- `README.md` — Bundle format documentation

Also available via the API (`GET /api/export`) and the Export button on the Stats page.

## License

MIT
