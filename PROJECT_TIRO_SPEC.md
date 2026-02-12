# Project Tiro — Claude Code Build Spec

## Overview

**Project Tiro** is a local-first, open-source, model-agnostic reading OS for the AI age. Named after Cicero's freedman who preserved and organized his master's works for posterity, Tiro helps users save, process, understand, and resurface web content and email newsletters — owned entirely on their machine, queryable by any AI model.

**Hackathon context:** Built solo for the "Built with Opus 4.6: Claude Code Hackathon" (Feb 10–16, 2026). Must be fully open source, built from scratch during the event. Judged on Impact (25%), Opus 4.6 Use (25%), Depth & Execution (20%), Demo (30%).

**Core principles:**
- Local-first: all data lives on the user's machine (markdown files, SQLite, ChromaDB)
- Model-agnostic data layer: content stored in open formats (markdown + structured metadata), portable and usable with any AI
- Opinionated intelligence layer: showcases Opus 4.6 for the deep reasoning tasks (digests, analysis, cross-document insight)
- Minimal friction: single command to run, minimal dependencies, clean reader UI

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Web UI (Frontend)                    │
│  FastAPI serves React/HTML at localhost:8000             │
│  - Inbox view (all articles, daily digest, grouped)     │
│  - Reader view (summary + full article + side panel)    │
│  - Search bar (semantic search)                         │
│  - Source management (VIP starring)                     │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API
┌──────────────────────┴──────────────────────────────────┐
│                  FastAPI Backend (Python)                 │
│                                                          │
│  Ingestion Engine                                        │
│  ├── Web page connector (readability + markdownify)      │
│  ├── Email connector (.eml parsing)                      │
│  └── [Future: RSS, YouTube, Podcasts]                    │
│                                                          │
│  Intelligence Layer (Opus 4.6 via Anthropic API)         │
│  ├── Daily digest generation                             │
│  ├── Ingenuity/trust analysis (on-demand)                │
│  └── Learned preference classification                   │
│                                                          │
│  Lightweight Processing (Haiku / local model)            │
│  ├── Tag extraction                                      │
│  ├── Named entity extraction                             │
│  ├── Basic summarization                                 │
│                                                          │
│  Query Layer                                             │
│  ├── Semantic search (ChromaDB)                          │
│  ├── Metadata search (SQLite)                            │
│  └── MCP server (exposes knowledge base to Claude)       │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                    Storage Layer                          │
│                                                          │
│  /tiro-library/                                          │
│  ├── articles/          # Markdown files (source of truth)│
│  │   ├── 2026-02-11_article-slug.md                      │
│  │   └── ...                                             │
│  ├── tiro.db            # SQLite (metadata, preferences) │
│  ├── chroma/            # ChromaDB (vector embeddings)   │
│  └── config.yaml        # User configuration             │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend framework | FastAPI | Async, fast, good ecosystem, Python-native |
| Content extraction | `readability-lxml` + `markdownify` | Mozilla Readability algorithm, no LLM needed |
| Email parsing | Python `email` stdlib + `readability-lxml` | Parse .eml files, extract HTML body, same pipeline |
| Structured storage | SQLite | Zero config, embedded, perfect for local-first |
| Vector storage | ChromaDB | Embedded, no server, stores vectors + metadata |
| Embeddings | `sentence-transformers` (local) or Anthropic API | Local preferred for cost; API as fallback |
| Intelligence (heavy) | Claude Opus 4.6 via Anthropic API | Digests, analysis, cross-document reasoning |
| Intelligence (light) | Claude Haiku 4.5 via Anthropic API | Tag extraction, entity extraction, basic summaries |
| Frontend | Minimal HTML/CSS/JS served by FastAPI | Or lightweight React if time permits; distraction-free reader |
| MCP | Python MCP SDK | Expose Tiro knowledge base to Claude Desktop / Claude Code |

### Key Python packages
```
fastapi
uvicorn
readability-lxml
markdownify
chromadb
sentence-transformers
anthropic
python-frontmatter
pyyaml
aiofiles
```

---

## Data Models

### SQLite Schema

```sql
-- Sources (domains, newsletter senders)
CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- e.g., "Stratechery", "Matt Levine"
    domain TEXT,                     -- e.g., "stratechery.com"
    email_sender TEXT,               -- e.g., "ben@stratechery.com"
    source_type TEXT NOT NULL,       -- "web" | "email" | "rss"
    is_vip BOOLEAN DEFAULT FALSE,   -- VIP sources get priority everywhere
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Articles (core content metadata)
CREATE TABLE articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    title TEXT NOT NULL,
    author TEXT,
    url TEXT,                        -- original URL if web
    slug TEXT UNIQUE NOT NULL,       -- filename-safe identifier
    markdown_path TEXT NOT NULL,     -- relative path to .md file
    summary TEXT,                    -- AI-generated summary
    word_count INTEGER,
    reading_time_min INTEGER,        -- estimated minutes to read (word_count / 250)
    published_at TIMESTAMP,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- User interaction
    is_read BOOLEAN DEFAULT FALSE,
    rating INTEGER,                  -- -1 (dislike), 1 (like), 2 (love)
    opened_count INTEGER DEFAULT 0,
    -- AI classification (populated by learned preferences)
    ai_tier TEXT,                    -- "must-read" | "summary-enough" | "discard"
    relevance_weight REAL DEFAULT 1.0, -- decay weight, reduced over time for unengaged articles
    -- Ingenuity analysis (populated on-demand)
    ingenuity_analysis TEXT          -- JSON blob from Opus analysis
);

-- Tags (extracted topics)
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL        -- normalized lowercase
);

CREATE TABLE article_tags (
    article_id INTEGER REFERENCES articles(id),
    tag_id INTEGER REFERENCES tags(id),
    PRIMARY KEY (article_id, tag_id)
);

-- Named entities (people, companies, orgs)
CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,       -- "person" | "company" | "organization" | "product"
    UNIQUE(name, entity_type)
);

CREATE TABLE article_entities (
    article_id INTEGER REFERENCES articles(id),
    entity_id INTEGER REFERENCES entities(id),
    PRIMARY KEY (article_id, entity_id)
);

-- Daily digests (cached)
CREATE TABLE digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,              -- YYYY-MM-DD
    digest_type TEXT NOT NULL,       -- "ranked" | "by_topic" | "by_entity"
    content TEXT NOT NULL,           -- Markdown content of the digest
    article_ids TEXT NOT NULL,       -- JSON array of article IDs included
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, digest_type)
);

-- Article relationships (related articles via similarity)
CREATE TABLE article_relations (
    article_id INTEGER REFERENCES articles(id),
    related_article_id INTEGER REFERENCES articles(id),
    similarity_score REAL,           -- cosine similarity from ChromaDB
    connection_note TEXT,            -- Opus-generated connection description
    PRIMARY KEY (article_id, related_article_id)
);

-- Reading stats (daily aggregates for the stats dashboard)
CREATE TABLE reading_stats (
    date TEXT NOT NULL,              -- YYYY-MM-DD
    articles_saved INTEGER DEFAULT 0,
    articles_read INTEGER DEFAULT 0,
    articles_rated INTEGER DEFAULT 0,
    total_reading_time_min INTEGER DEFAULT 0,  -- sum of reading_time_min of read articles
    PRIMARY KEY (date)
);
```

### Markdown File Format

Each saved article is stored as a markdown file with YAML frontmatter:

```markdown
---
title: "The Future of AI Agents"
author: "Ben Thompson"
source: "Stratechery"
url: "https://stratechery.com/2026/the-future-of-ai-agents"
published: 2026-02-10
ingested: 2026-02-11T14:30:00
tags: ["ai", "agents", "software"]
entities: ["Anthropic", "OpenAI", "Ben Thompson"]
word_count: 2450
reading_time: 10 min
---

# The Future of AI Agents

[Full article content in clean markdown...]
```

### ChromaDB Collection

```python
collection = chroma_client.get_or_create_collection(
    name="tiro_articles",
    metadata={"hnsw:space": "cosine"}
)

# Each article stored as:
collection.add(
    ids=["article_42"],
    documents=["full article text..."],
    metadatas=[{
        "title": "The Future of AI Agents",
        "source": "Stratechery",
        "is_vip": True,
        "tags": "ai,agents,software",  # comma-separated for filtering
        "published_at": "2026-02-10",
        "article_id": 42
    }]
)
```

---

## API Endpoints

```
# Ingestion
POST   /api/ingest/url          # Save a web page by URL
POST   /api/ingest/email        # Upload .eml file(s)
POST   /api/ingest/batch-email  # Point to a directory of .eml files

# Articles
GET    /api/articles             # List all articles (filterable, sortable)
GET    /api/articles/:id         # Get single article with full content
PATCH  /api/articles/:id/rate    # Set rating: { "rating": -1 | 1 | 2 }
PATCH  /api/articles/:id/read    # Mark as read / increment open count

# Sources
GET    /api/sources              # List all sources
PATCH  /api/sources/:id/vip     # Toggle VIP status

# Intelligence (Opus 4.6)
GET    /api/digest/today         # Generate or retrieve today's digest
GET    /api/digest/today/:type   # Specific digest type: ranked | by_topic | by_entity
GET    /api/articles/:id/analysis  # On-demand ingenuity/trust analysis

# Search
GET    /api/search?q=...         # Semantic search across all articles

# Related articles
GET    /api/articles/:id/related # Get related articles with connection notes

# Preferences (learned)
POST   /api/classify             # Run Opus classification on unrated articles

# Stats
GET    /api/stats?period=...     # Reading stats (week | month | all)

# Export
GET    /api/export               # Download library as zip (filterable)

# Digest delivery
POST   /api/digest/send          # Send today's digest via email
```

---

## Implementation Tiers

### Tier 0 — Core Pipeline (Days 1–2)

This is the foundation. Nothing else works without this.

#### 0.1 Project scaffolding
- FastAPI app structure with proper project layout
- SQLite database initialization with schema above
- ChromaDB client initialization
- Config file loading (config.yaml for API keys, library path, etc.)
- Single entry point: `python -m tiro` or `python run.py`

#### 0.2 Web page ingestion
- `POST /api/ingest/url` accepts a URL
- Fetch page HTML (use `httpx` for async)
- Extract main content using `readability-lxml` (strips nav, ads, boilerplate)
- Convert to clean markdown using `markdownify`
- Preserve links (convert to markdown links), images (as references), code blocks
- Generate slug from title + date
- Compute reading time estimate: `word_count / 250` (rounded up to nearest minute)
- Save markdown file to `articles/` directory with YAML frontmatter
- Insert metadata into SQLite (including `reading_time_min`)
- Generate embedding and store in ChromaDB

#### 0.3 Lightweight AI processing at ingest
- Call Haiku to extract: tags (3-8 topic tags), named entities (people, companies, orgs, products), and a 2-3 sentence summary
- Single API call with structured output (JSON)
- Store tags and entities in SQLite junction tables
- Store summary in articles table and as part of frontmatter
- Identify or create source record; associate article with source

#### 0.4 Source management with VIP
- Auto-detect source from URL domain
- `sources` table with `is_vip` flag
- API endpoint to toggle VIP
- VIP status propagates to article queries (VIP articles sort first)

#### 0.5 Basic web UI — Inbox view
- Clean, minimal, distraction-free design
- Inbox-style list of all articles: title, source, date, reading time estimate, summary preview, tags
- VIP source articles visually distinguished (subtle star or accent)
- Sortable by date (default: newest first, VIP pinned to top)
- Dislike / Like / Love buttons on each article row (Netflix-style, persist to SQLite)
- Click article to navigate to reader view

#### 0.6 Basic web UI — Reader view
- Summary displayed prominently at top (card or highlighted block)
- Full markdown article rendered below (use a markdown renderer)
- Clean typography, readable line width, distraction-free
- Back button to inbox

---

### Tier 1 — Intelligence Layer (Days 3–4)

This is the Opus 4.6 showcase. The demo lives or dies here.

#### 1.1 Daily digest generation (Opus 4.6)
- `GET /api/digest/today` triggers Opus to generate three digest variants:
  1. **Ranked by importance**: All recent unread articles ordered by Opus's assessment of significance, with VIP sources weighted higher. Each entry has a 1-2 sentence reason for its ranking.
  2. **Grouped by topic**: Articles clustered by theme/tag with cross-references noted. Opus should call out when multiple articles discuss the same topic from different angles or reach different conclusions.
  3. **Grouped by entity**: Articles organized by the companies/people/orgs they discuss, with relationship mapping between entities.
- **Prompt design**: Send Opus the summaries + metadata of all recent articles (not full text — save tokens). Include user's VIP sources and recent ratings as context. Ask for markdown output with links back to each article.
- Cache generated digests in `digests` table (regenerate on demand or when new articles are ingested).
- **This is the "wow" moment**: Opus finding contradictions between sources, connecting threads across unrelated newsletters, surfacing insights the user would have missed.

#### 1.2 Digest UI
- Tabs or sections in the inbox view: "All Articles" | "Today's Digest" | "By Topic" | "By Entity"
- Digest views render the Opus-generated markdown
- Each article mentioned in the digest links to its reader view
- VIP source articles are called out with visual indicator in digest

#### 1.3 Ingenuity/trust analysis (Opus 4.6, on-demand)
- Info icon on each article that triggers `GET /api/articles/:id/analysis`
- Sends full article text to Opus with a structured prompt requesting:
  - **Bias indicators**: Political lean, emotional language use, one-sided framing, missing perspectives
  - **Factual confidence**: Claims that are well-sourced vs. unsourced assertions, potential misinformation flags
  - **Novelty assessment**: Is this reporting new information, synthesizing existing knowledge, or rehashing known content?
- Returns structured JSON rendered as a side panel in the reader view
- Results cached in `ingenuity_analysis` column (JSON blob)
- **Not precomputed** — only runs when user requests it (saves API costs)

#### 1.4 Semantic search
- Search bar in the UI header
- `GET /api/search?q=...` queries ChromaDB for semantically similar articles
- Returns ranked results with relevance scores and text snippets
- Results displayed in inbox-style format with match highlights

#### 1.5 Related articles engine
- When a new article is saved, automatically query ChromaDB for the top 3-5 most similar existing articles
- Store relationships in a new `article_relations` table (article_id, related_article_id, similarity_score, relation_type)
- On the reader view, display a "Related in your library" section below the article
- Optionally, on ingest, send the new article's summary + related article summaries to Opus to generate a brief connection note (e.g., "This contradicts [Article X]'s claim that..." or "Builds on the framework discussed in [Article Y]")
- This is the serendipity engine — it makes the library feel alive and interconnected
- Also surface related articles in the digest when Opus identifies cross-document threads
- **API**: `GET /api/articles/:id/related` returns related articles with similarity scores and connection notes

---

### Tier 2 — Email Newsletter Connector (Days 4–5)

#### 2.1 Email ingestion pipeline
- `POST /api/ingest/email` accepts uploaded .eml file
- `POST /api/ingest/batch-email` accepts a directory path of .eml files
- Pipeline: parse .eml → extract HTML body (Python `email` stdlib) → `readability-lxml` → `markdownify` → same storage pipeline as web pages
- Extract sender info to auto-create/match source records
- Handle common newsletter quirks: tracking pixels, UTM params, wrapper HTML

#### 2.2 Demo data pipeline
- Script to export a batch of newsletters from Gmail as .eml files (can be manual export or a simple IMAP fetch script)
- Bulk import command: `python -m tiro import-emails ./my-newsletters/`
- This populates the library with real content for a compelling demo

---

### Tier 3 — Polish & Power Features (Days 5–6)

#### 3.1 MCP server
- Expose Tiro's knowledge base as an MCP server that Claude Desktop or Claude Code can connect to
- Tools to expose:
  - `search_articles(query)` — semantic search
  - `get_article(id)` — full article content
  - `get_digest(type)` — today's digest
  - `get_articles_by_tag(tag)` — filtered retrieval
  - `get_articles_by_source(source)` — source-filtered retrieval
- This enables conversations like: "What have my saved articles said about AI regulation this week?" directly in Claude

#### 3.2 Learned preferences (Opus 4.6)
- `POST /api/classify` sends Opus:
  - Examples of articles the user rated (Dislike, Like, Love) with their summaries and sources
  - VIP source list
  - Unrated articles to classify
- Opus returns a tier for each: "must-read" | "summary-enough" | "discard"
- Stored in `ai_tier` column
- UI surfaces these classifications: must-reads prominently, summary-enough as collapsed summaries, discards hidden (with option to show)
- Re-run periodically or on demand as user provides more ratings

#### 3.3 Knowledge graph visualization (stretch)
- Extract entity-to-entity and entity-to-topic relationships from articles
- Build a force-directed graph (d3.js) showing:
  - Nodes: entities and topics
  - Edges: co-occurrence in articles
  - Node size: frequency of mention
  - Clusters: naturally forming topic groups
- Interactive: click a node to see all related articles
- This is visually stunning for the demo if time allows

#### 3.4 Chrome Extension (stretch)
- Minimal Chrome extension with a "Save to Tiro" button in the toolbar
- On click: grabs the current page URL and sends a `POST /api/ingest/url` to the locally running Tiro server
- Optional: popup shows confirmation with extracted title and source, lets user mark source as VIP before saving
- Manifest V3, minimal permissions (activeTab + localhost network access)
- Structure: `extension/manifest.json`, `popup.html`, `popup.js`, `background.js`, `icon.png`
- This is the "Pocket-like" entry point that makes daily use frictionless
- **Keep it dead simple** — no auth, no settings, just save. The intelligence lives in the backend.

#### 3.5 Packaging & Installation
- Package Tiro for easy installation by non-developer users:
  - `uv pip install tiro-reader` (PyPI package) or at minimum a clean `uv pip install -e .` with `pyproject.toml`
  - Single setup command: `tiro init` creates the library directory, initializes databases, prompts for API key
  - `tiro run` starts the server and opens the browser
  - `tiro import-emails ./path/to/emails/` for bulk import
- Include a clear README with:
  - Prerequisites (Python 3.11+, uv, API key)
  - One-liner install + run
  - Screenshots of the UI
  - Architecture overview for contributors
- Docker option as a stretch: `docker-compose up` for zero-dependency setup
- CLI entry points via `pyproject.toml` `[project.scripts]` so `tiro` commands work globally after install

#### 3.6 Keyboard-first navigation
- Full keyboard bindings throughout the UI:
  - `j` / `k` — move up/down through article list
  - `Enter` — open selected article
  - `b` or `Escape` — back to inbox
  - `s` — toggle VIP on current article's source
  - `1` / `2` / `3` — dislike / like / love
  - `/` — focus search bar
  - `d` — switch to digest view
  - `?` — show keyboard shortcuts overlay
- Highlight the currently selected article in the inbox with a subtle visual indicator
- This makes Tiro feel like a power-user tool (think Vim, Superhuman, or Hey email)

#### 3.7 Content decay system
- Add a `relevance_weight` REAL column to the `articles` table, defaulting to 1.0
- Articles the user never opens or rates decay over time: multiply by 0.95 per day after 7 days of no engagement
- Articles the user rated (Like/Love) are immune to decay; Disliked articles decay faster (0.9 per day)
- VIP source articles decay slower (0.98 per day)
- Relevance weight factors into digest ranking — decayed articles drop naturally without manual cleanup
- Periodic background task recalculates weights (on server start or via endpoint)
- `GET /api/articles` supports `?include_decayed=false` to hide very low-weight articles (threshold: 0.1)

#### 3.8 Reading stats dashboard
- New UI page/tab: "Stats"
- Show reading patterns over time using simple charts (Chart.js or lightweight inline SVGs):
  - Articles saved per week (bar chart)
  - Articles read vs. saved ratio (line chart)
  - Top topics this month (horizontal bar chart by tag frequency)
  - Top sources by engagement (sources you Love most vs. Dislike most)
  - Reading streak (consecutive days with at least one article read)
- Data sourced from `reading_stats` table (updated on each read/save/rate action)
- Light, informative — helps users understand their own information diet
- **API**: `GET /api/stats?period=week|month|all`

#### 3.9 Export to markdown bundle
- `GET /api/export` generates a zip file of the user's library:
  - All markdown files with frontmatter intact
  - `metadata.json` with full SQLite data (articles, tags, entities, ratings, sources, relations)
  - `README.md` explaining the bundle format
- Filterable: `?tag=ai`, `?source_id=5`, `?rating_min=1`, `?date_from=2026-01-01`
- This is the ultimate expression of the "own your context" principle — your data, fully portable, no lock-in
- Also enables: backup, migration to another system, sharing curated collections
- **CLI**: `tiro export --output ./my-backup.zip --tag ai`

#### 3.10 Scheduled digest email delivery
- Optional feature: send the daily digest to the user's email each morning
- Configure in `config.yaml`: `digest_email: "user@example.com"`, `digest_schedule: "08:00"`
- Use Python `smtplib` with a simple local SMTP config or a free transactional service (Resend, Mailgun free tier)
- The digest is already generated (Tier 1.1) — this just delivers it in a new channel
- Ironic to use email, but it meets the user where they already are every morning
- For the hackathon demo: can show this working with a local mailhog/mailtrap instance
- **API**: `POST /api/digest/send` to trigger a manual send

#### 3.11 UI polish
- Responsive design
- Dark mode
- Keyboard shortcuts (j/k navigation, s to star source as VIP, 1/2/3 for dislike/like/love)
- Loading states and error handling

---

## Out of Scope for Hackathon

These are explicitly excluded from the hackathon build but mentioned in the demo as the Tiro vision. See the full Future Roadmap at the end of this document.

---

## Configuration (config.yaml)

```yaml
# Tiro Configuration
library_path: "./tiro-library"    # Where all data is stored

# API Keys
anthropic_api_key: "sk-..."       # Required for Opus & Haiku
# embedding_model: "local"        # "local" (sentence-transformers) or "anthropic"

# Server
host: "127.0.0.1"
port: 8000

# Ingestion defaults
default_embedding_model: "all-MiniLM-L6-v2"   # sentence-transformers model

# Intelligence
opus_model: "claude-opus-4-6"
haiku_model: "claude-haiku-4-5-20251001"

# Content decay
decay_rate_default: 0.95       # daily multiplier after 7 days no engagement
decay_rate_disliked: 0.90      # faster decay for disliked articles
decay_rate_vip: 0.98           # slower decay for VIP source articles
decay_threshold: 0.1           # hide articles below this weight

# Digest email (optional)
# digest_email: "you@example.com"
# digest_schedule: "08:00"     # 24h format, local time
# smtp_host: "localhost"
# smtp_port: 1025              # e.g., mailhog for local dev
```

---

## Demo Script (3 minutes)

**[0:00–0:30] Hook & Context**
"I'm a solo builder, and Claude Code was my CTO for this project. In 6 days, we built Tiro — a local-first reading OS for the AI age. Think Pocket, but with Opus 4.6 as your personal research librarian."

**[0:30–1:00] Live Ingestion**
Save 2-3 articles by URL in the UI. Show the markdown output, extracted tags, entities, and summary appearing in real time. "Everything lives on your machine as clean markdown files. No cloud, no lock-in."

**[1:00–1:30] The Opus 4.6 Moment — Daily Digest**
Trigger digest generation on a library of ~30 pre-loaded newsletters. Show Opus finding thematic threads across sources, surfacing a contradiction between two newsletters, and ranking by relevance with VIP sources weighted. "This is what only Opus 4.6 can do — deep cross-document reasoning over my entire reading history."

**[1:30–2:00] Reader + Analysis**
Open an article, show the clean reader with summary. Trigger the ingenuity analysis — show the bias/factual/novelty panel appearing. "On-demand intelligence, not precomputed. You choose when to spend the tokens."

**[2:00–2:30] Search + MCP**
Semantic search across the library. Then switch to Claude Code with MCP connected: "What have my newsletters said about AI regulation this week?" — Claude answers from Tiro's knowledge base. "Your reading, queryable by any AI."

**[2:30–3:00] Vision & Close**
"Tiro is open source, local-first, and model-agnostic at the data layer. Today it handles web pages and newsletters. Tomorrow: RSS, podcasts, video transcripts. The name comes from Cicero's freedman who preserved and organized his works — helping them survive to the Renaissance. Tiro does the same for your digital knowledge."

---

## Project Structure

```
tiro/
├── run.py                    # Entry point: starts FastAPI server
├── config.yaml               # User configuration
├── README.md
├── LICENSE                   # Open source license (MIT or Apache 2.0)
│
├── tiro/
│   ├── __init__.py
│   ├── app.py                # FastAPI app initialization
│   ├── config.py             # Config loading
│   ├── database.py           # SQLite initialization and helpers
│   ├── vectorstore.py        # ChromaDB initialization and helpers
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── web.py            # Web page ingestion (readability + markdownify)
│   │   ├── email.py          # Email/newsletter ingestion (.eml parsing)
│   │   ├── processor.py      # Common processing pipeline (save md, embed, extract)
│   │   └── extractors.py     # Tag, entity, summary extraction (Haiku calls)
│   │
│   ├── intelligence/
│   │   ├── __init__.py
│   │   ├── digest.py         # Daily digest generation (Opus 4.6)
│   │   ├── analysis.py       # Ingenuity/trust analysis (Opus 4.6)
│   │   ├── preferences.py    # Learned preference classification (Opus 4.6)
│   │   └── prompts.py        # All prompt templates in one place
│   │
│   ├── search/
│   │   ├── __init__.py
│   │   └── semantic.py       # ChromaDB search interface
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   └── server.py         # MCP server exposing Tiro tools
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes_articles.py
│   │   ├── routes_ingest.py
│   │   ├── routes_sources.py
│   │   ├── routes_digest.py
│   │   ├── routes_search.py
│   │   ├── routes_classify.py
│   │   ├── routes_stats.py
│   │   └── routes_export.py
│   │
│   └── frontend/
│       ├── static/
│       │   ├── styles.css     # Minimal, distraction-free styling
│       │   └── app.js         # Frontend logic
│       └── templates/
│           ├── index.html     # Inbox view
│           ├── reader.html    # Article reader view
│           ├── stats.html     # Reading stats dashboard
│           └── base.html      # Base template
│
├── scripts/
│   ├── import_emails.py       # Bulk .eml import utility
│   └── seed_demo.py           # Seed library with demo content
│
├── extension/                 # Chrome Extension (stretch goal)
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.js
│   ├── background.js
│   └── icons/
│
├── pyproject.toml             # Package config with CLI entry points
│
└── tiro-library/              # Default library location (gitignored)
    ├── articles/
    ├── tiro.db
    ├── chroma/
    └── config.yaml
```

---

## Key Prompt Templates

### Tag & Entity Extraction (Haiku)

```
You are analyzing a saved article for a personal reading library. Extract structured metadata.

Article title: {title}
Article content: {content_truncated_to_2000_chars}

Respond with JSON only, no other text:
{
  "tags": ["tag1", "tag2", ...],       // 3-8 lowercase topic tags
  "entities": [
    {"name": "Entity Name", "type": "person|company|organization|product"}
  ],
  "summary": "2-3 sentence summary of the article's key points."
}
```

### Daily Digest (Opus 4.6)

```
You are Tiro, a personal reading assistant. Generate a daily digest of the user's saved articles.

## User Context
- VIP sources (always prioritize): {vip_sources}
- Recent ratings: {recent_ratings_with_summaries}

## Today's Articles
{for each article: id, title, source, is_vip, tags, entities, summary, published_date}

## Task
Generate three digest sections in markdown:

### 1. Ranked by Importance
Order all articles by significance to this reader. Consider:
- VIP sources should be weighted higher
- User's demonstrated interests from ratings
- Timeliness and impact of the content
For each article, include a 1-sentence reason for its position.

### 2. Grouped by Topic
Cluster articles by theme. For each cluster:
- Name the theme
- List articles with brief context
- **Call out cross-references**: where articles discuss the same topic from different angles, reach different conclusions, or where one article's claims contradict another's

### 3. Grouped by Entity
Organize by the key people, companies, and organizations discussed.
Note when the same entity appears across multiple sources with different coverage.

Format all article references as links: [Article Title](/articles/{id})
```

### Ingenuity/Trust Analysis (Opus 4.6)

```
You are a media literacy analyst. Evaluate this article across three dimensions.

Article: {full_article_text}
Source: {source_name}

Respond with JSON:
{
  "bias": {
    "score": 1-10,        // 1 = very biased, 10 = very balanced
    "lean": "left|center-left|center|center-right|right|non-political",
    "indicators": ["list of specific bias indicators found"],
    "missing_perspectives": ["perspectives not represented"]
  },
  "factual_confidence": {
    "score": 1-10,        // 1 = mostly unsourced claims, 10 = well-sourced throughout
    "well_sourced_claims": ["claims with clear evidence or citations"],
    "unsourced_assertions": ["claims presented as fact without backing"],
    "flags": ["any potential misinformation or misleading framing"]
  },
  "novelty": {
    "score": 1-10,        // 1 = entirely rehashed, 10 = breaking new ground
    "assessment": "Brief description of what's new vs. known",
    "novel_claims": ["genuinely new information or synthesis"]
  },
  "overall_summary": "2-sentence overall assessment of this article's trustworthiness and value."
}
```

### Learned Preferences Classification (Opus 4.6)

```
You are learning a user's reading preferences to classify new articles.

## Articles the user LOVED (rating: 2)
{loved_articles_with_summaries_and_sources}

## Articles the user LIKED (rating: 1)
{liked_articles_with_summaries_and_sources}

## Articles the user DISLIKED (rating: -1)
{disliked_articles_with_summaries_and_sources}

## VIP Sources (always prioritize)
{vip_source_list}

## Articles to Classify
{unrated_articles_with_summaries_and_sources}

For each article, classify into one tier:
- "must-read": User would want to read this in full. Matches their interests, from VIP sources, or high-impact content.
- "summary-enough": Worth knowing about but the summary captures sufficient value.
- "discard": Unlikely to interest this user based on their demonstrated preferences.

Respond with JSON:
{
  "classifications": [
    {"article_id": 1, "tier": "must-read", "reason": "brief explanation"},
    ...
  ]
}
```

---

## Build Order & Checkpoints

When building with Claude Code, follow this order. Each checkpoint should result in something testable.

1. **Checkpoint: Skeleton runs** — FastAPI starts, serves a "Tiro is running" page at localhost:8000, SQLite and ChromaDB initialize on first run.

2. **Checkpoint: Can save a URL** — POST a URL, get back a clean markdown file in `articles/`, metadata in SQLite (including reading time), embedding in ChromaDB. Verify by checking the file and querying the DB.

3. **Checkpoint: Inbox shows articles** — Web UI lists all saved articles with title, source, date, reading time, summary. VIP toggle works. Rating buttons (Dislike/Like/Love) work.

4. **Checkpoint: Reader works** — Click an article, see summary + full content rendered cleanly. Back button returns to inbox.

5. **Checkpoint: Digest generates** — Hit the digest endpoint, Opus produces a ranked + grouped digest. Digest tab in UI renders it with links to articles.

6. **Checkpoint: Analysis works** — Click info icon on an article, Opus returns bias/factual/novelty assessment, side panel renders it.

7. **Checkpoint: Search + Related** — Semantic search returns relevant articles. Related articles surface in the reader view with connection notes.

8. **Checkpoint: Email import works** — Point at a directory of .eml files, they get processed through the same pipeline.

9. **Checkpoint: MCP server connects** — Claude Code can query Tiro's knowledge base via MCP tools.

10. **Checkpoint: Learned preferences** — After rating some articles, Opus classifies unrated ones into tiers. UI reflects the classification.

11. **Checkpoint: Keyboard navigation** — Full j/k/enter/b navigation working across inbox and reader. Shortcuts overlay on `?`.

12. **Checkpoint: Content decay** — Relevance weights update on server start. Old unengaged articles drop in digest rankings. Decay-filtered view works.

13. **Checkpoint: Reading stats** — Stats page renders charts showing reading patterns over time. Data updates on each user action.

14. **Checkpoint: Export works** — `GET /api/export` returns a zip with all markdown files and metadata. Filterable by tag/source/rating.

15. **Checkpoint: Chrome extension** — Extension installed, clicking "Save to Tiro" on any page sends it to the local server and it appears in the inbox.

16. **Checkpoint: Packaging** — `uv pip install -e .` works, `tiro init` and `tiro run` CLI commands work, README has clear setup instructions.

17. **Checkpoint: Digest email** — Scheduled digest sent to configured email. Visible in mailhog/mailtrap for demo.

---

## Notes for Claude Code

- **Use `uv` for all Python version and dependency management** — never use pip directly. Use `uv pip install`, `uv venv`, `uv run`, etc.
- **Python 3.11+** — use modern Python features (type hints, match statements, f-strings)
- **Async throughout** — FastAPI is async, so use `async def` for route handlers and `httpx` for HTTP calls
- **Error handling** — graceful failures on network issues, malformed HTML, API rate limits. Never crash the server.
- **Logging** — use Python `logging` module, INFO level by default, DEBUG available via config
- **Tests** — if time permits, add basic pytest tests for the ingestion pipeline and API endpoints
- **README** — clear setup instructions: clone, `uv pip install -e .`, add API key to config, `tiro run`. Should take under 2 minutes.
- **License** — MIT (simple, permissive, hackathon-friendly)
- **Demo data** — include the `seed_demo.py` script that populates the library with sample articles for judging

---

## Future Roadmap

Everything below is out of scope for the hackathon but represents the full vision for Tiro. Items that made it into the hackathon build plan are not repeated here. Organized by category, roughly priority-ordered within each.

### Ingestion & Connectors

- **RSS feed connector**: Subscribe to RSS/Atom feeds, auto-ingest new posts on a configurable schedule. Natural next connector after web + email.
- **YouTube connector**: Fetch transcripts (via `youtube-transcript-api` or Whisper), process as articles with timestamped sections. Support saving specific timestamp ranges.
- **Podcast connector**: Download audio → transcribe (Whisper) → process as article. Preserve episode metadata, show notes, and guest information.
- **Twitter/X thread connector**: Unroll and save threads as coherent articles with embedded media references.
- **PDF connector**: Ingest PDFs (research papers, reports) with OCR fallback for scanned documents. Extract citations and references.
- **Advanced browser extension**: Beyond the hackathon's basic "Save to Tiro" button — add right-click "Save selection to Tiro" for partial page saves, auto-detect newsletter content on webmail pages, suggested saves based on browsing patterns.
- **Readwise import**: One-time migration path for Readwise/Reader users to bring their existing library into Tiro.
- **OPML import**: Import existing RSS subscription lists for quick setup.

### Intelligence & AI Features

- **Author-level VIP**: VIP flagging at the author level, not just source/domain. Track a specific writer across publications.
- **Scroll depth tracking**: Fine-grained reading behavior — how far users scroll, time spent per section, which parts they re-read. Feed this as signal into the preference model for much richer understanding.
- **PageRank-style link scoring**: Build an authority graph from hyperlinks preserved within saved articles. Sources that are frequently cited by other saved articles gain authority. Surface these as "foundational sources" in the knowledge graph.
- **Multi-model comparison**: Run the same analysis prompt through multiple models (Opus, Sonnet, GPT-4, Gemini) and show how different models interpret the same content. Useful for reducing bias in the AI layer itself.
- **Argument mapping**: For opinion pieces and analysis, have Opus extract the logical structure — premises, evidence, conclusions, unstated assumptions. Render as a visual argument map.
- **Temporal analysis**: Track how coverage of a topic evolves over time across your sources. "Here's how your newsletters' stance on AI regulation shifted from January to March."
- **Contradiction alerts**: Proactive notifications when a newly saved article contradicts claims in an article you previously rated highly. Don't wait for digest time — flag it immediately.
- **Reading pattern insights**: Weekly/monthly AI-generated report on your reading habits — what topics you're gravitating toward, which sources you engage with most, blind spots in your information diet.

### Frontend & UX

- **Highlights and annotations**: Select text in the reader to highlight, add margin notes. Store as structured data linked to article + text position. Exportable.
- **Highlight-based digests**: Generate summaries not from full articles but from what the user actually highlighted. Much more personalized.
- **Dark mode**: System-preference-aware dark theme with manual toggle.
- **Mobile-responsive reader**: Clean reading experience on phone/tablet — the place where most reading actually happens.
- **Offline mode**: Service worker caching so saved articles are readable without a network connection. The local-first architecture makes this natural.
- **Customizable inbox views**: User-defined filters and saved views (e.g., "VIP sources this week", "Unread tech articles", "Loved articles about AI").
- **Obsidian integration**: Sync Tiro's markdown files + knowledge graph with an Obsidian vault. Bidirectional — notes in Obsidian can reference Tiro articles and vice versa.

### Infrastructure & Distribution

- **Remote access via Tailscale**: Run Tiro on your home server/desktop but access it from anywhere (phone, tablet, laptop) through a Tailscale mesh VPN. Zero port forwarding, zero cloud servers — your device talks directly to your machine over an encrypted tunnel. Pairs naturally with a mobile-responsive frontend. The dream: save an article from your phone on the subway, have it processed by your home server's GPU, read the Opus-generated digest on your commute home.
- **Desktop app (Tauri)**: Wrap the web UI in a native desktop shell for a more polished local experience. Auto-starts the backend.
- **Docker packaging**: `docker-compose up` for zero-dependency deployment. Include ChromaDB and SQLite in the container.
- **Cloud sync (optional)**: User-controlled sync of the library directory to their own storage (S3, Dropbox, Google Drive, iCloud). Tiro never touches a server the user doesn't own.
- **Multi-device**: With cloud sync, access the same library from multiple machines. Conflict resolution via last-write-wins on metadata, append-only on ratings.
- **Plugin system**: Allow community-contributed connectors, analysis modules, and UI themes. Define a clean plugin API for each layer (ingestion, intelligence, display).

### Social & Sharing

- **Collaborative sharing**: Share curated digests or article collections with others. Export a digest as a shareable web page or newsletter.
- **Reading groups**: Shared libraries for teams or communities. See what others are saving and how they're rating. Collaborative knowledge building.
- **Public reading lists**: Optionally publish your VIP sources and top-rated articles as a public feed others can follow.

### Data & Privacy

- **Full data export (advanced)**: Beyond the hackathon's zip export — include digests, analysis results, and reading stats in the bundle. Support CSV and JSON formats alongside markdown.
- **Data deletion**: Easy purge of individual articles, sources, or entire history. When you delete, it's actually gone — no ghost data.
- **Local-only embeddings**: Default to local embedding models (sentence-transformers) so no content ever leaves the machine for vector generation.
- **Encrypted storage**: Optional encryption-at-rest for the SQLite database and ChromaDB store. For users with sensitive reading material.
- **Audit log**: Track every API call made to external services (Anthropic, etc.) with timestamps and token counts. Full transparency on what data leaves your machine.
