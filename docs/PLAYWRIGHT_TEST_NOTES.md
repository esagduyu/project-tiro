# Playwright Test Notes — 2026-02-15

Comprehensive end-to-end testing of all functionality built in Checkpoints 1–13, performed via Playwright MCP browser automation against `localhost:8000`.

---

## 1. Homepage / Inbox View

**Status: PASS**

- Page title: "Tiro — Inbox"
- Header: "Tiro" logo link, "your reading, organized" tagline, "Stats" nav link
- View tabs: "All Articles" (active by default), "Daily Digest"
- Search bar with placeholder "Search your library..."
- Controls: Reclassify button, Show discarded (2), Show archived, Sort dropdown
- Article cards verified:
  - Tier badges: "Must Read" (green border), "Summary" (indigo border)
  - Source type pills: blue "saved", pink "email" — correctly colored
  - Source names displayed (stratechery.com, paulgraham.com, darioamodei.com, etc.)
  - VIP stars (filled gold for VIP sources)
  - Dates formatted correctly (e.g. "Feb 11", "Jan 15", "Dec 31, 2025")
  - Reading time estimates (e.g. "21 min", "14 min")
  - TL;DR summaries styled as **TL;DR** – *italic text*
  - Tags displayed as clickable pills
  - Rating buttons: heart (love), + (like), - (dislike)
- 15 articles visible by default (2 discard-tier hidden, 1 decayed hidden)
- Only cosmetic error: missing favicon.ico (404)

## 2. Reader View

**Status: PASS**

- Tested with "DeepSeek FAQ" article (id=24)
- Article header: title, source with VIP star, date, reading time
- Original URL link (↗ stratechery.com)
- Tags displayed as clickable pills
- TL;DR summary present
- Full article content rendered via marked.js:
  - External links open correctly
  - Blockquotes rendered properly
  - Code elements (`R1`, `V3`, etc.) rendered inline
  - Lists rendered correctly
- Action buttons: analysis (i), love, like, dislike
- "Related in your library" section at bottom:
  - 5 related articles with similarity scores (80%, 72%, 72%, 72%, 66%)
  - Haiku-generated connection notes for top 3
  - Links navigate to correct article pages
- Analysis panel:
  - Opens via i button
  - Shows intro page with 3 dimensions explanation
  - "Run Ingenuity Analysis with Opus 4.6" button
  - Cached results displayed: Bias 5/10, Factual Confidence 8/10, Novelty 7/10
  - Collapsible sections with chevron indicators
  - Score-colored summary (aggregate and per-dimension)

**Bug found (fixed):** `loadInbox()` in app.js threw `TypeError: Cannot read properties of null (reading 'style')` because it ran on the reader page where inbox DOM elements don't exist. Fixed by adding `if (!listEl) return;` guard.

## 3. Digest View

**Status: PASS**

- Switched via "Daily Digest" tab
- Three sub-tabs: Ranked, By Topic, By Entity

### Ranked variant
- Numbered articles with links to reader view
- VIP star indicators inline
- Insightful cross-article commentary by Opus 4.6
- "Generated 8h ago" banner with Regenerate button

### By Topic variant
- Themed clusters: Anthropic Moment, US-China Tech Competition, AI's Impact on Work, Financial Markets, Startup Strategy
- Cross-references between articles
- Contradiction alerts between conflicting viewpoints

### By Entity variant
- Entity-organized sections: Anthropic/Dario Amodei/Claude, OpenAI, Ben Thompson/Stratechery, Microsoft, DeepSeek/China, Paul Graham, TSMC/Taiwan, Google/Gemini
- Cross-source analysis per entity
- Links to relevant articles

## 4. Search

**Status: PASS**

- Typed "AI safety and alignment" in search bar
- Results appeared with similarity badges (74%, 68%, 67%, etc.)
- Top result: "Dario Amodei - Machines of Loving Grace" (74%) — semantically correct
- "Results for" header with count ("9 found")
- Source type pills and tier badges preserved in search results
- Clear button (x) returns to full article list
- Debounced input (300ms delay)

## 5. Keyboard Navigation

**Status: PASS**

### Inbox shortcuts tested:
- `j` (x3): selection moved down through articles with blue `.kb-selected` highlight
- `k`: selection moved up one
- `?`: shortcuts overlay appeared with Navigation, Actions, General sections
- `Escape`: closed overlay
- `Enter`: opened selected article
- `Escape` (in reader): navigated back to inbox

### Shortcuts overlay content verified:
- Navigation: j/k (move), Enter (open), / (search), d (digest), a (articles), g (stats)
- Actions: s (VIP), 1/2/3 (rate), c (classify), r (regenerate digest)
- General: ? (help), Esc (blur/close)

## 6. Stats Page

**Status: PASS (after bug fix)**

- Summary cards: 1 Saved, 5 Read, 1 Rated, 1h 24m Reading time, 1 Day streak
- Period dropdown: Last 7 days, Last 30 days (default), All time — all load data
- 4 Chart.js charts:
  1. **Articles saved** (bar): blue bar on Feb 15 showing 1 article
  2. **Read vs Saved** (line): green line spikes to 5 reads, blue shows 1 saved — distinct colors with legend
  3. **Top topics** (horizontal bar): "ai" leads with 4, followed by "artificial intelligence" (3), then 8 topics at 2 each
  4. **Sources by engagement** (stacked horizontal bar): stratechery.com (2 loves), Matt Levine (1 love), darioamodei.com (1 love), paulgraham.com (1 love + 1 like + 1 dislike) — purple/green/red stacked bars with legend
- Keyboard: `b`/`Esc` back to inbox, `?` shows shortcuts

**Bug found (fixed):** All 4 charts had `backgroundColor` with 0.15 alpha opacity — bars were nearly invisible on white background. Pixel sampling confirmed alpha of 38/255. Fixed by increasing opacity to 0.55–0.6. Verified via screenshot that all charts are now clearly visible.

## 7. API Endpoints

**Status: PASS**

All endpoints tested via `fetch()` in browser console:

| Endpoint | Result |
|----------|--------|
| `GET /api/articles` | 18 articles returned |
| `GET /api/sources` | 9 sources returned |
| `GET /api/search?q=China` | 9 search results |
| `GET /api/articles/24/related` | 5 related articles with similarity scores |
| `GET /api/digest/today` | Digest with ranked data |
| `GET /api/articles/24` | Full article with content, source_type, ai_tier |
| `POST /api/decay/recalculate` | Success |
| `GET /api/articles?include_decayed=false` | 17 articles (1 decayed below threshold) |
| `GET /api/articles/24/analysis?cache_only=true` | Cached bias analysis data |
| `GET /api/stats?period=all` | daily_counts, totals, top_tags, top_sources, reading_streak |

All responses follow `{"success": true, "data": ...}` pattern.

## 8. Sort and Filter Controls

**Status: PASS**

### Sort dropdown
- **Newest first** (default): VIP articles pinned first, then by date descending
- **Oldest first**: VIP articles pinned first, then by date ascending (Dec 16, 2025 → Feb 15, 2026)
- **By importance**: must-read (10) → summary-enough (5) → discard (hidden); VIP pinned within each tier

### Show discarded toggle
- Button shows count: "Show discarded (2)"
- Click reveals 2 discard-tier articles at bottom ("How to Do Great Work", "How to Think for Yourself")
- Discarded articles have no tier badge (correct)
- Button text changes to "Hide discarded (2)" with active state
- Toggle hides them again

### Show archived toggle
- Button: "Show archived"
- Click reveals 1 decayed article: "Superlinear Returns" (paulgraham.com, Dec 16, 2025)
- Discarded count increases from 2 to 3 — confirms documented gotcha: "Show archived" force-shows discarded articles too (articles can be both decayed AND discard-tier)
- Total articles: 18 (all visible)
- Button text changes to "Hide archived" with active state

### Client-side re-sorting
- Sort changes are instant (no API re-fetch) — uses `cachedArticles` JS variable
- Sort dropdown value syncs when switching modes

---

## Bugs Found

### Bug 1: Stats chart opacity (FIXED)

- **File:** `tiro/frontend/templates/stats.html`, lines 85–93
- **Symptom:** All 4 Chart.js charts appeared blank/invisible
- **Root cause:** `chartColors` object used `rgba(..., 0.15)` for all background colors — only 15% opacity, invisible on white
- **Fix:** Increased all `*Light` color opacities to 0.55–0.6
- **Verification:** Screenshot confirms all 4 charts clearly visible with distinct colors

### Bug 2: app.js loadInbox null error (FIXED)

- **File:** `tiro/frontend/static/app.js`, line 191
- **Symptom:** `TypeError: Cannot read properties of null (reading 'style')` on reader page
- **Root cause:** `loadInbox()` called from `DOMContentLoaded` in `app.js` (loaded via `base.html` on all pages), but accesses `#article-list` which doesn't exist on `reader.html`
- **Fix:** Added `if (!listEl) return;` guard at top of `loadInbox()`
- **Verification:** 0 console errors on reader page after fix

### Bug 3: Missing favicon.ico (NOT FIXED — low priority)

- **Symptom:** 404 on `/favicon.ico` request
- **Impact:** Cosmetic only — no functional impact
- **Status:** Deferred

---

## Cache Bust Version

Bumped from v=22 to v=23 in:
- `tiro/frontend/templates/base.html` (styles.css, app.js)
- `tiro/frontend/templates/reader.html` (reader.js)

---

## Environment

- **Server:** `uv run python run.py` on `localhost:8000`
- **Browser:** Playwright MCP (Chromium)
- **Library:** 18 articles from 9 sources (mix of web saves and email imports)
- **Data state:** 5+ rated articles, classification complete, decay calculated, digest cached
