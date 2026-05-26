# Project Tiro — Product Roadmap

Review date: 2026-05-25
Updated: 2026-05-25 (post-strategy review)
Status: Hackathon top-30 (out of ~500); invited to SF. Transitioning from demo to public alpha.

## How To Use This Document

Each phase below is **self-contained**: a planning agent should be able to read the front matter (Executive Summary, Product Strategy, Principles, Codebase Health) plus a single phase section and produce an executable plan without consulting other phases.

For each phase you will find:

- **Goal** — one sentence describing the outcome.
- **Why this phase, why now** — strategic justification and dependencies on earlier phases.
- **In scope** — concrete deliverables, with file paths from the current codebase where relevant.
- **Out of scope** — explicit non-goals to prevent scope creep.
- **Dependencies** — prerequisite phases or features.
- **Acceptance criteria** — testable conditions that define "done."
- **Test plan** — what must be verified and how.
- **Risks and gotchas** — known pitfalls, including any from `CLAUDE.md`.
- **Release target** — version label.

Phases are ordered by product impact, not engineering effort. No wall-clock time estimates are given because agents can run continuously; instead each phase is labeled with **Relative Complexity** (S / M / L / XL) so phases can be sequenced and resourced.

When a phase calls for changes in code already documented in `CLAUDE.md`, the agent should re-read that file and the relevant module before planning. The "Gotchas" sub-section in each phase highlights the most likely traps but is not exhaustive.

## Executive Summary

Tiro is a local-first, model-agnostic reading OS. The hackathon build (17 spec checkpoints + 6 beyond-spec) shipped a complete demo: article and newsletter ingestion, AI enrichment via Claude Opus/Haiku, three-variant daily digests, semantic search, knowledge graph, reading stats, TTS audio, Gmail integration, MCP server, Chrome extension, and a Roman-themed responsive UI.

The product thesis works. The architecture is coherent. The remaining question is **trust**: can this be installed by another human, run for months, and hold their reading life without losing data, leaking secrets, or breaking silently?

The roadmap below is a path from "impressive demo" to "Obsidian-style local-first product with optional paid hosted convenience." It begins with a security release because the current build has working features layered on a localhost-only threat model that no longer matches LAN/phone/daemon use cases. It then prioritizes the features that change daily usage (highlights, RSS, private remote) before the features that change delivery (desktop packaging, cloud sync), because installing an app you do not yet love is friction.

## Product Strategy

Tiro is positioned as a personal reading OS with three deploy modes:

1. **Tiro Local** — free, open-source, fully local. Users run it on their laptop or home server. They bring their own API keys or use local models.
2. **Tiro Private Remote** — still self-hosted, but easy to reach from phone/tablet through Tailscale or another private network. This is the bridge between local-first and daily use.
3. **Tiro Cloud** — paid hosted sync, backups, sharing, and managed AI baseline. The business value is convenience and reliability, not locking up the user's data.

The product promise: original source files remain clean and portable; user-created memory (highlights, notes, ratings, digests, AI outputs) lives in adjacent local files and transparent databases; anything paid makes the system easier to run across devices, not worse to own locally.

## Product Principles

- **Local-first, cloud-optional** — local use must remain first-class and never feel like a trial.
- **Source-preserving** — never mutate the original saved article markdown to store personal data. Use sidecars.
- **Bring-your-own-AI by default** — API keys, local models, and external assistants must all be supported.
- **Hosted AI as convenience** — paid AI should be a bundled baseline, not the only path.
- **Agentic but inspectable** — agents leave logs, cited inputs, outputs, and replayable traces.
- **Private remote before public sharing** — phone access through private networks matters before collaborative/social features.
- **Plain-file escape hatch** — export, backup, and Obsidian-style interoperability are core product features, not afterthoughts.

## External Product Assumptions

- **Tailscale Serve** is the default recommendation for private access; it exposes a local service only inside the user's tailnet. **Tailscale Funnel** is useful later for public sharing but is a distinct risk class because it exposes a service to the broader internet. See Tailscale's docs for [Serve](https://tailscale.com/docs/reference/tailscale-cli/serve) and [Funnel](https://tailscale.com/docs/features/tailscale-funnel).
- **Claude paid plans and the Anthropic API are separate products.** A Claude Pro or Max subscription is not a backend API entitlement. See Anthropic's [Claude paid plans vs. API access](https://support.anthropic.com/en/articles/8114521-how-can-i-access-the-claude-api). Tiro must not treat consumer subscriptions as automation surfaces.
- **OpenAI's agent direction** points toward tool-using workflows, evals, and embeddable agent experiences. Tiro should expose its library through tools and agent contracts rather than only direct one-off model calls. See [OpenAI Agents documentation](https://platform.openai.com/docs/guides/agents).
- **MCP remains strategically important** because it lets external assistants use Tiro as a knowledge tool. See the [Claude Code SDK MCP docs](https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-mcp).

## Codebase Health Summary

Verified during this review:

**Strengths**
- Clean module boundaries: ingestion, intelligence, search, export, stats, TTS, MCP, API routes are separate.
- Expensive AI work moved off the event loop via `asyncio.to_thread()`.
- Background tasks (IMAP, digest scheduler) created/cancelled in FastAPI lifespan.
- `CLAUDE.md` and `docs/plans/` preserve unusually high-quality design memory and root-cause notes.
- Storage portable: markdown files + SQLite + ChromaDB.

**Severe issues (block public alpha)**
- No authentication. `tiro/app.py:184` sets `allow_origins=["*"]` with `allow_credentials=True`. Any browser tab can call any endpoint. LAN mode (`--lan`) makes this worse.
- No article deletion anywhere in `tiro/api/`. Local-first ownership without delete is product-broken.
- Markdown rendered with `marked.parse()` → `innerHTML` in `reader.js` and `app.js`. XSS via hostile saved articles will run in the Tiro origin.
- Ingestion is not atomic across markdown file, SQLite row, ChromaDB vector, stats, and AI metadata. Partial failures leave orphans in any of four stores.
- Settings routes (`tiro/api/routes_settings.py`) hardcode `Path("config.yaml")`, ignoring the active `--config` path.

**Quality issues (papercuts)**
- Stats inflate on every read/rate write (not only on first transition). Re-opening articles inflates `articles_read` and reading time.
- IMAP background task starts only at startup; enabling IMAP via Settings does not start it (digest scheduler does this correctly — pattern exists to copy).
- Custom theme settings are persisted but `applyTheme()` hardcodes built-in names; cache busting is at `v=39` in `app.js` while `base.html` is at `v=46`.
- `marked`, Chart.js, and d3.js loaded from CDN — undermines offline/local-first.
- Duplicated `parse_model_json()` patterns across `analysis.py`, `digest.py`, `preferences.py`.
- Two separate query paths (`/api/search` vs `/api/articles`) make combined semantic+filter UX hard.

**Test coverage**
- Zero automated tests. `playwright-tests/` contains 39 screenshot artifacts, no test code. Manual visual verification only.

---

## Phase 0 — Security & Integrity Release

**Release target:** `0.2 alpha`
**Relative complexity:** XL
**Goal:** Make Tiro safe to install on a multi-device network, with a working data-lifecycle (delete, repair, recover), tested at the seams where current bugs live.

### Why this phase, why now

None of the product-grade distribution work should happen while any browser tab can mutate the user's Gmail credentials, hostile article HTML can run inside the app, or the only way to "delete" an article is to manually edit three databases and a directory. This is the prerequisite for everything else. The work also unlocks the planning of every later phase because adding new features on top of partial-state bugs is wasted effort.

The original review treated delete as Phase 1. We've moved it here because "local-first ownership" without delete is a product lie. The other Phase-1 items (source merge, advanced repair, full export) remain in Phase 1.

### In scope

**Authentication & origin protection** (the security spine):

- Single-user password auth: bcrypt-hashed password stored in `config.yaml` under `auth.password_hash`. First-run sets it. CLI command `tiro set-password` to reset.
- Session cookie (HttpOnly, Secure when over HTTPS, SameSite=Lax) for browser sessions. Sliding expiry, default 30 days.
- API token (random 32-byte URL-safe) for non-browser clients: Chrome extension, MCP server, CLI scripts. Stored hashed; presented once at creation. Multiple tokens supported.
- Lock down CORS in `tiro/app.py`: default `allow_origins` to `["http://localhost:8000", "http://127.0.0.1:8000"]`. Add token-listed origins for the Chrome extension (`chrome-extension://<id>`) configurable in `config.yaml`.
- CSRF protection for cookie-authenticated browser mutations: double-submit token or rely on SameSite=Lax + checking `Origin`/`Referer` headers. Pick one and document.
- LAN mode (`--lan`) must refuse to start without auth configured, unless explicit `--insecure-no-auth` is passed (with a startup warning printed every time).
- Chrome extension popup updates to handle token auth: settings tab to paste token, store in `chrome.storage.local`, send as `Authorization: Bearer <token>` on every request.
- MCP server (`tiro/mcp/server.py`) accepts token via env var `TIRO_API_TOKEN` (does not need to call API — it talks to SQLite/ChromaDB directly, but it should still respect the same single-user gating so misconfigured Desktop setups don't expose data via stale processes).

**Markdown sanitization** (XSS fix):

- Add DOMPurify (vendored, see "Vendor frontend deps" below) and run it after `marked.parse()` in both `tiro/frontend/static/reader.js` and `tiro/frontend/static/app.js`.
- Configure marked to disallow raw HTML where possible (`marked.setOptions({ ... })`).
- Sanitize again on the server during ingestion: strip `<script>`, `<iframe>`, event handlers, `javascript:` URLs from the saved markdown. Keep images, links, formatting.
- Apply the same sanitization to Opus-generated digest markdown before storing.

**Article deletion** (the product-credibility fix):

- New endpoint: `DELETE /api/articles/{id}`.
- New CLI: `tiro delete <id>` and `tiro delete --source <id>` (for bulk source delete in Phase 1; foundation here).
- Deletion must clean all stores: SQLite (`articles`, `article_tags`, `article_entities`, `article_relations`, `audio`), ChromaDB vector, markdown file under `articles/`, audio MP3 under `audio/`. Wrap in a single transaction-like coordinator with explicit rollback on failure (best-effort across non-transactional stores).
- Reader UI gets a delete button (with confirmation modal explaining permanence). Inbox gets keyboard shortcut `x` (after current selection) and bulk delete via checkbox + toolbar.
- Add SQLite foreign keys with `ON DELETE CASCADE` to junction tables in `tiro/database.py` where missing — but do not rely on them alone; the coordinator still handles markdown/ChromaDB/audio.

**Atomic ingestion** (the four-store consistency fix):

- Refactor `tiro/ingestion/processor.py` `process_article()` into explicit stages with rollback:
  1. Compute slug, check duplicate (read-only).
  2. Write markdown to temp file `articles/.{slug}.md.tmp`.
  3. Insert article + source rows in a single SQLite transaction. Capture article_id.
  4. `os.rename()` temp file to final path (atomic on POSIX).
  5. Call Haiku for tags/entities/summary.
  6. Update SQLite + frontmatter with extracted metadata.
  7. Add to ChromaDB. On failure, mark article with `vector_status='pending'` and continue (background retry).
  8. Compute related articles and store relations.
  9. Update stats (idempotent — see Stats below).
- On failure at any stage after the rename, the cleanup runs the same path as article deletion to leave no orphans.
- Add `articles.vector_status` column: `pending | indexed | failed`. Background task retries pending vectors every N minutes.

**`tiro doctor` repair command** (the recovery fix):

- New CLI: `tiro doctor` walks all four stores and reports inconsistencies.
- `tiro doctor --fix` performs repairs:
  - Markdown files without DB rows → move to `articles/.orphaned/` or delete with confirmation.
  - DB rows without markdown files → mark broken and offer deletion.
  - ChromaDB vectors with no matching article → delete.
  - Articles with no vector → re-embed.
  - Audio rows with missing MP3 → clean row.
  - MP3 files with no row → delete or re-register.
- Output is human-readable and machine-parseable (`--json` flag).

**Settings path correctness**:

- Store `config_path` on `app.state` during config load in `tiro/app.py`.
- Refactor `tiro/api/routes_settings.py` to use a shared `persist_config(state, updates)` helper that writes to the active path. Helper preserves comments and field order (use `ruamel.yaml` not stdlib `yaml`).
- Same fix for `tts`, `email`, `digest-schedule`, `appearance` settings.

**Stats idempotency**:

- In `tiro/api/routes_articles.py`, before incrementing read/rating stats, read the previous values.
- `articles_read` and `reading_time_minutes` increment only on the `is_read: 0 → 1` transition.
- `articles_rated` increments only on the `rating: NULL → not NULL` transition. Rating changes do not increment.
- Optional: rename to `rating_actions` if total writes are wanted somewhere — but the dashboard meaning is "articles you rated," so transition counting is correct.

**Dynamic IMAP scheduler**:

- Mirror the digest-scheduler pattern (`app.state.digest_task`): store `app.state.imap_task` and add start/stop logic to `tiro/api/routes_settings.py` when email settings change.
- When IMAP is enabled or `imap_sync_interval` changes, restart the task. When disabled, cancel it.
- An immediate check after enable is optional UX polish (toast + check fires).

**Vendor frontend dependencies** (local-first integrity):

- Move CDN libraries (`marked`, Chart.js, d3.js, DOMPurify) into `tiro/frontend/static/vendor/` with pinned versions. Add a short README documenting versions and upgrade procedure.
- Update `base.html` and `inbox.html`/`digest.html`/`reader.html`/`graph.html`/`stats.html` references.
- Add SRI hashes to any remaining CDN script tags. Strongly prefer none.

**Test harness bootstrap** (zero → minimum viable):

- Add `pytest`, `pytest-asyncio`, `httpx` to dev deps in `pyproject.toml`.
- Create `tests/` directory with `conftest.py` providing fixtures: temp `library_path`, isolated SQLite, isolated ChromaDB, FastAPI `TestClient`.
- Required test coverage for this phase:
  - `tests/test_auth.py` — password hashing, session cookie, token validation, CORS rejection, CSRF.
  - `tests/test_ingestion.py` — happy path; failure at each stage leaves no orphans; duplicate URL handling.
  - `tests/test_delete.py` — create article, delete article, assert no residue in any store.
  - `tests/test_doctor.py` — seed inconsistencies, run doctor --fix, assert clean.
  - `tests/test_stats.py` — first-read transition increments; subsequent reads do not; rating-change does not double-count.
  - `tests/test_settings.py` — config writes go to the active `--config` path; YAML comments preserved.
  - `tests/test_sanitize.py` — `<script>` and `javascript:` URLs stripped from saved markdown and digest output.
  - `tests/test_smoke.py` — server starts, key endpoints respond authenticated, reject unauthenticated.
- One Playwright smoke test (in `playwright-tests/` as a real `.spec.js`, not a screenshot) verifying login, save article, read, delete.

### Out of scope

- Multi-user accounts (single-user only, this release).
- OAuth / SSO.
- Source merge, source rename, author normalization (Phase 1).
- Backup snapshots (Phase 1).
- Notes and highlights (Phase 1 follow-on, actually Phase 2 here).
- RSS, OPML (Phase 3).
- Desktop packaging (Phase 4).

### Dependencies

None. This is the foundation phase.

### Acceptance criteria

- Server refuses unauthenticated requests to any `/api/*` route except `POST /api/auth/login` and a `/healthz`.
- Hostile `<script>alert(1)</script>` saved in an article does not execute in the reader.
- `DELETE /api/articles/{id}` followed by `tiro doctor` reports zero inconsistencies.
- Crashing the server during `process_article()` and restarting leaves no orphans visible to `tiro doctor`.
- `uv run tiro --config /tmp/test.yaml run`, then changing TTS voice via the Settings UI, results in the new voice persisted in `/tmp/test.yaml` (not `./config.yaml`).
- Opening the same article ten times increments `articles_read` by 1, not 10.
- Enabling IMAP via Settings begins polling within one sync interval, without restart.
- `pytest` runs green; coverage report committed.
- All vendored deps work with the dev server offline (disconnect network, reload, verify).

### Test plan

- All unit/integration tests above.
- Manual Playwright run of: fresh install → set password → save URL → read → highlight → rate → delete → confirm gone.
- Run `tiro doctor` on the demo seed library, verify clean.
- LAN-mode integration test: start with `--lan`, attempt connection from a second device, confirm auth challenge.

### Risks and gotchas

- **DOMPurify config affects existing articles**: aggressive stripping may remove `<img>` width/height attributes used in reader styling. Test on the demo library before rolling out.
- **`marked` + DOMPurify ordering**: sanitize the HTML output, not the markdown input — sanitizing markdown breaks legitimate formatting.
- **ChromaDB rollback is best-effort**: ChromaDB has no transaction primitives. The coordinator should delete added vectors on failure but accept that a hard crash mid-`add()` can leave one orphan. `tiro doctor` is the safety net.
- **`ON DELETE CASCADE` requires pragma**: SQLite foreign keys are off by default. `tiro/database.py` already enables them in `get_connection()`, but every connection must do this — verify across the codebase.
- **Session cookie + Chrome extension**: extensions cannot share cookies with web pages by default. Extension uses bearer token, browser uses cookie. Two auth paths, one auth backend.
- **Stats idempotency may break the demo seed**: the seed script may rely on bumping counters. Update `scripts/seed_articles.py` to set state directly in SQL.
- **`config_path` change touches every settings handler**: easy to miss one. Grep for `Path("config.yaml")` after the refactor and assert zero hits.
- **CLAUDE.md warns about ChromaDB readonly DB errors in uvicorn** — pre-initializing the library with `tiro init` works around it. The atomic ingestion refactor must not regress this.

---

## Phase 1 — Local Library Integrity

**Release target:** `0.3 local-beta`
**Relative complexity:** L
**Goal:** Make the local-first data promise credible end-to-end: rename, merge, restore, back up.

### Why this phase, why now

Phase 0 made delete work. Phase 1 extends the data-lifecycle to the operations a user performs after they've lived with their library for months: "this source is actually the same as that source," "I changed my mind, restore that article," "I want to back up before doing something risky." Without these, the local library accumulates inconsistency that even `tiro doctor` cannot fix because the source-of-truth is ambiguous.

This phase also closes the export story (notes/highlights are not in it yet — they arrive in Phase 2). Backups precede notes intentionally: notes are higher stakes, and a user who has highlighted an article cares much more about not losing it.

### In scope

**Source management**:
- `DELETE /api/sources/{id}` — removes the source row and cascades to its articles (with confirmation in the UI showing the article count).
- `POST /api/sources/merge` body `{from: id, into: id}` — re-points all articles from one source to another, removes the orphaned source row.
- `PATCH /api/sources/{id}` body `{name, domain, email_sender, source_type}` — rename and edit. UI in Settings or a new `/sources` page.
- Author normalization: detect close matches across sources (same `email_sender` with different display names) and offer merge.

**Backup snapshots**:
- New CLI: `tiro backup --output ~/tiro-backups/{date}.tar.zst` — full library snapshot (markdown + SQLite + ChromaDB + config minus secrets + audio metadata, optionally including audio MP3s with `--include-audio`).
- New CLI: `tiro restore <snapshot>` — replaces current library after confirmation. Existing library moved to `tiro-library.bak.{ts}`.
- Automatic backup hook before destructive operations: source delete, bulk delete, reclassify-with-clear, restore. Stored under `~/.tiro/backups/auto/` with a configurable retention (default: keep last 10).
- New endpoint: `GET /api/backup/snapshots` — list snapshots with sizes and dates.

**Full export expansion**:
- Extend `tiro/export.py` to include: highlights (Phase 2 will populate), notes (Phase 2), digests (all dates), analyses (`ingenuity_analysis` column), audio metadata, graph nodes/edges, stats history.
- Add OPML export of all sources (forward-looking for Phase 3 RSS).
- Export format documented in a `tiro/export/SCHEMA.md` so importers can be built.

**Import**:
- `tiro import <snapshot>` reverses export. Conflict resolution: skip / overwrite / keep both (with suffix).
- Foundation for Phase 3 third-party imports (Pocket, Instapaper, Readwise) — they will use the same import infrastructure.

### Out of scope

- Notes and highlights (Phase 2).
- RSS subscriptions (Phase 3).
- Cloud sync (Phase 6).
- Multi-device merge (Phase 6).

### Dependencies

- Phase 0 complete: delete must work, atomic ingestion must work, `tiro doctor` must work.

### Acceptance criteria

- `tiro backup` produces a snapshot; `tiro restore` of that snapshot on a wiped library produces an identical state (verified by hashing markdown files + diffing SQLite dumps).
- Merging source A into source B leaves zero references to A in any table.
- `tiro export` round-trips through `tiro import` with no data loss.
- All operations covered by tests; `tiro doctor` clean after each.

### Test plan

- `tests/test_backup.py` — backup, wipe, restore, assert identity.
- `tests/test_source_merge.py` — merge with overlapping articles and dedup.
- `tests/test_export_roundtrip.py` — full library → export → import → diff.
- Manual UI test of source delete confirmation, source merge UI.

### Risks and gotchas

- **ChromaDB is not portable across versions**. Backup must export embeddings as a portable format (JSON of `id, embedding, metadata`) and re-add them on restore, not copy ChromaDB's internal SQLite. This was already a sore point — see `CLAUDE.md` "ChromaDB readonly database" note.
- **Audio MP3s are large**. Default backup excludes them; opt-in only.
- **Source merge across `source_type`** (web vs email) is ambiguous — same author publishes blog and newsletter. Force user to pick the target type.
- **Restore must invalidate caches** — digest cache, audio cache, analysis cache. Cleanest: clear all caches on restore.

---

## Phase 2 — Highlights & Notes

**Release target:** `0.4 reader-memory-beta`
**Relative complexity:** L
**Goal:** Make Tiro a place to think, not just a place to save.

### Why this phase, why now

Highlights and notes create the retention loop. A user who has highlighted ten articles will not switch readers; a user who has only saved them will. Every other phase below benefits from this existing (RSS items become highlight-worthy; agent runtime gets a new corpus to summarize; cloud sync becomes meaningfully personal).

This phase comes before desktop packaging (Phase 5) because packaging an app whose feature surface has not changed since 0.3 will not move adoption. Notes + highlights make the desktop install worth doing.

### In scope

**Data model**:
- New table `highlights`: `id, article_id, quote_text, prefix_context, suffix_context, text_position_start, text_position_end, content_hash, color, created_at, updated_at`.
- New table `notes`: `id, article_id, highlight_id (nullable), body_markdown, created_at, updated_at`.
- `highlight_id NULL` means article-level note; otherwise it is anchored to a highlight.
- Sidecar files (source of truth for portability):
  - `notes/{slug}.md` — user's article-level notes in markdown.
  - `annotations/{slug}.jsonl` — one annotation per line: `{id, quote, prefix, suffix, position, hash, color, note_id, timestamps}`. SQLite is a derived index, not the source of truth.
- On startup, reconcile sidecars → SQLite (sidecars win on conflict).

**Reader UI**:
- Text selection in the reader pops a toolbar: highlight (color picker: yellow, green, blue, pink), add note, copy quote.
- Highlights persist visually on reload using `Range` reconstruction from anchors.
- Margin notes panel: clicking a highlight opens its note (or creates one).
- Article-level note: button in reader header, opens drawer.
- Notes are markdown with live preview.

**Anchor robustness** (the hard problem):
- Primary anchor: surrounding text (prefix + selected quote + suffix), per W3C Annotation Model TextQuoteSelector pattern.
- Secondary anchor: text position offset within the article markdown.
- Tertiary anchor: content hash of article markdown (detects drift).
- Reconciliation order on load: text-quote match → position fallback → hash-mismatch warning shown to user with "find similar text" UI.

**Highlight review**:
- New view `/highlights` showing all highlights, filterable by article/source/color/date.
- "Highlight digest" — extend digest generation to include a weekly highlight summary section.
- Keyboard shortcut `h` opens highlight view.

**Export/import**:
- Highlights and notes included in `tiro export` (Phase 1 expansion already planned this).
- Markdown export option: append highlights as blockquotes under article frontmatter for Obsidian compatibility.

**MCP exposure**:
- New tool `get_highlights` in `tiro/mcp/server.py` — agents can read user highlights as context.

### Out of scope

- Spaced repetition / flashcards (post-1.0 unless explicit user demand).
- Highlight sharing or social features.
- AI-generated highlight suggestions (Phase 6 agent runtime could add this).
- Voice notes (post-1.0).

### Dependencies

- Phase 0 complete (sanitization required — highlights contain user-written markdown that gets rendered).
- Phase 1 complete (export schema must accommodate highlights/notes).

### Acceptance criteria

- Highlight a paragraph, reload, highlight persists.
- Edit the article markdown by hand, reload — highlight either re-anchors (if quote still present) or surfaces a warning (if not).
- Notes are markdown-editable and rendered safely.
- Sidecar files in `notes/` and `annotations/` are human-readable.
- Round-trip: export → wipe → import preserves all highlights and notes.

### Test plan

- `tests/test_highlights.py` — anchor reconciliation: exact, position-only, hash-mismatch, missing.
- `tests/test_notes.py` — markdown sanitization, sidecar/DB sync.
- Playwright: select text → highlight → reload → assert highlight present at same location.
- Manual: hand-edit a `notes/` sidecar; restart server; assert SQLite picks up the change.

### Risks and gotchas

- **Reader currently re-renders markdown to HTML on every load**. Highlights apply to the *rendered DOM*, not the markdown. Must use a deterministic markdown → HTML render so positions are stable, or render once and cache the HTML alongside the article.
- **DOMPurify (Phase 0) strips some attributes**. If we add `data-highlight-id` attributes to spans, allowlist them.
- **Hash drift from upstream updates**: if a user re-saves an article and it changed, do we re-anchor highlights from the old version? Decision: no — version the article, keep highlights pinned to the version they were made against, surface a "newer version available" UI.
- **`Range` reconstruction across DOM types**: highlights spanning element boundaries (e.g. across a `<p>` break) need careful range serialization. Use [rangy](https://github.com/timdown/rangy) or equivalent, vendored.

---

## Phase 3 — Private Remote Access

**Release target:** `0.5 private-remote-beta`
**Relative complexity:** M
**Goal:** Let users run Tiro on a laptop or home machine and read it from their phone without giving up local ownership.

### Why this phase, why now

This is the product wedge. "Read on phone while the library stays on your machine" is the killer use case that distinguishes local-first from cloud-first readers. It is also the natural bridge to paid Tiro Cloud: users who don't want to manage Tailscale can pay for hosted access.

The phase is sequenced after highlights because highlighting on a phone is the actual mobile UX worth building. Without highlights, the phone experience is a read-only viewer — much less compelling.

This is a Medium-complexity phase, not Large: most of it is a setup wizard plus PWA manifest work on top of features that already exist.

### In scope

**Private Remote setup wizard** (`/setup/remote` in the web UI):
- Detect Tailscale presence: `tailscale status --json` via subprocess.
- If installed: show the `tailscale serve` command tailored to the current Tiro port. Optional: execute it on the user's confirmation.
- Store the resulting Tailscale URL in config (`remote_url`).
- Test reachability: HEAD request from the server to itself via the Tailscale URL.
- If Tailscale is not installed: link to installation instructions, show an alternative manual port-forwarding warning.

**LAN-mode hardening**:
- `--lan` now requires auth (already enforced by Phase 0).
- Startup prints the LAN IP, the auth URL, and a warning that unencrypted HTTP is in use unless behind Tailscale/HTTPS.
- A persistent banner in the UI when bound to `0.0.0.0` without HTTPS, dismissable per-session.

**QR code login**:
- `/setup/qr` generates a QR code containing the Tiro URL + one-time login token (15-minute TTL).
- Scanning it on a phone opens the URL, validates the token, logs in, stores a session cookie. Token is single-use.

**Mobile PWA polish**:
- `tiro/frontend/static/manifest.webmanifest` with name, icons (use existing logo), `display: standalone`, theme colors from active theme.
- Service worker (`tiro/frontend/static/sw.js`) caching: shell HTML/CSS/JS + recently-viewed article markdown for offline reading.
- "Add to Home Screen" prompt UX.
- Reader: tap-target sizing, swipe-back gesture, thumb-friendly audio controls, persistent mini-player on scroll.
- Inbox: pull-to-refresh, infinite scroll already exists.
- Offline article queue: if a save fails (no network), queue locally and retry when online.

**HTTPS guidance**:
- Tailscale Serve provides HTTPS automatically. Document this as the recommended path.
- For LAN-only setups, document mkcert and provide a `tiro run --cert <path> --key <path>` option.
- Do not generate self-signed certs automatically (UX nightmare).

### Out of scope

- Public sharing (Tailscale Funnel) — document as advanced, do not build wizard.
- Native iOS/Android apps (PWA only this phase).
- Multi-device merge (Phase 6 cloud sync).
- WebAuthn / passkeys (post-1.0 unless user demand).

### Dependencies

- Phase 0 (auth, sanitization).
- Highlights (Phase 2) — phone is most valuable when it supports highlighting.

### Acceptance criteria

- A user with Tailscale on laptop + phone can run `tiro run`, complete the setup wizard, open the URL on their phone via Tailscale, log in via QR, save an article from the phone, highlight on the phone, and have it appear on the laptop within one refresh.
- LAN mode without auth refuses to start unless `--insecure-no-auth` passed.
- Service worker enables reading the last 50 articles offline on a phone with the app installed.

### Test plan

- Integration test for the QR login flow (token TTL, single-use).
- Manual cross-device test with two laptops on the same Tailscale tailnet.
- Lighthouse PWA audit ≥ 90.
- Manual offline test: install PWA, go offline, read previously-viewed article.

### Risks and gotchas

- **Tailscale is not always in `$PATH`** for the user running `uvicorn`. Detection must handle absence cleanly.
- **Subprocess call to `tailscale serve` requires elevated permissions** on some platforms. Show the command, do not always execute it.
- **Service worker cache invalidation** intersects with the `v=N` cache busting pattern in `base.html`. Update the SW to use the same version stamp.
- **The session cookie set on Tailscale URL is scoped to that hostname** — moving between Tailscale URL and direct LAN URL means re-auth. Document this.

---

## Phase 4 — Recurring Ingestion (RSS + Imports)

**Release target:** `0.6 feeds-beta`
**Relative complexity:** M
**Goal:** Make Tiro useful every morning without manual saving; bring users in via importable libraries from competing tools.

### Why this phase, why now

Two unrelated reasons grouped because they share infrastructure:

1. **Recurring ingestion (RSS/OPML)** creates daily return value. The current model requires the user to remember to save things; RSS makes the library fill itself overnight. Small engineering effort (a `feeds` table + `feedparser` + the existing scheduler pattern), high recurring value.

2. **Third-party imports (Pocket, Instapaper, Readwise)** are the acquisition channel. People with 5,000 Pocket items will try Tiro the day Pocket dies — or any day they decide to leave. Without an importer Tiro starts every user at zero.

Both build on Phase 1's import infrastructure.

### In scope

**RSS / Atom**:
- New table `feeds`: `id, url, title, last_fetched_at, last_etag, last_modified, status, error_count, source_id, fetch_interval_minutes`.
- New module `tiro/ingestion/rss.py` using `feedparser`.
- Background task in lifespan: `_rss_sync_loop()`, mirrors IMAP scheduler pattern. Per-feed `fetch_interval_minutes` (default 60).
- Feed entries flow through the same `process_article()` path. Use `link` as URL, `published_parsed` as `published_at`, feed title as source.
- Dedup by `entry.id` or canonical URL.
- Conditional GETs: send `If-None-Match` (etag) and `If-Modified-Since`.

**OPML**:
- `POST /api/feeds/import` accepts OPML file upload.
- `GET /api/feeds/export` returns OPML of all subscribed feeds.

**Feed management UI** (`/feeds`):
- List subscribed feeds with last-fetch, status, recent article count, pause toggle.
- Add feed by URL (with autodiscovery via `<link rel="alternate" type="application/rss+xml">`).
- Per-feed: fetch interval, mute, delete (with cascade option for its articles).

**Third-party imports**:
- `tiro import-pocket <export.html>` — Pocket's official HTML export.
- `tiro import-instapaper <export.csv>` — Instapaper CSV export.
- `tiro import-readwise <export.json>` — Readwise/Reader export.
- Each maps: URL → article (re-fetch and re-extract), tags → tags, highlights → highlights (Phase 2!), notes → notes (Phase 2!).
- Imports run in background with progress reporting.

**Advanced extension save**:
- Chrome extension: right-click context menu for "Save to Tiro" with submenus (Save, Save as VIP, Save with selection-as-highlight).
- Selection save: if the user has text selected, save the article and pre-create a highlight on that selection.
- Save-all-tabs button.

### Out of scope

- PDF ingestion (Phase 7).
- YouTube transcripts (Phase 7).
- Podcast transcription (Phase 7).
- Reverse-direction sync (Tiro → Readwise) — post-1.0.

### Dependencies

- Phase 1 (import schema).
- Phase 2 (so imports can carry highlights).
- IMAP scheduler pattern (already in `tiro/app.py`).

### Acceptance criteria

- Subscribing to 10 RSS feeds and waiting one cycle results in new articles ingested with correct sources and publish dates.
- OPML import of an exported feed list reproduces the same subscriptions.
- A Pocket export with 100 articles imports successfully, with re-fetched markdown and original timestamps.
- A Readwise export with 50 highlights imports highlights anchored correctly to articles.
- Feed errors do not stop other feeds; failure count and last error visible in `/feeds`.

### Test plan

- `tests/test_rss.py` — etag/last-modified handling, dedup, error backoff.
- `tests/test_opml.py` — round-trip.
- `tests/test_importers.py` — each importer with a small fixture file.
- Integration test: subscribe to a local test feed (served by `pytest` fixture), assert poll → article appears.

### Risks and gotchas

- **`feedparser` has security advisories around malformed feeds**. Pin a current version, fuzz with a few hostile feeds.
- **Re-fetching imported Pocket articles will fail for paywalled content**. Fall back to saving the Pocket extract if available; otherwise store as a stub with the original URL.
- **OPML nested folder structure** is common — flatten or preserve as tag prefixes? Recommendation: flatten on import, surface folder names as auto-tags.
- **RSS items often duplicate web saves**. Dedup by canonical URL across `articles.url` regardless of ingestion method.

---

## Phase 5 — Installable Personal App

**Release target:** `0.7 desktop-beta`
**Relative complexity:** L
**Goal:** Make Tiro easy for non-technical users to install, run continuously, and update.

### Why this phase, why now

By 0.7 the feature surface (auth, delete, notes, RSS, private remote) is worth installing. Before now, packaging would have been "the same demo, easier to install" — pure cost-of-distribution with no demand pull.

This phase deliberately follows highlights and RSS because both are daily-return loops that justify the install. Packaging precedes Tiro Cloud because the desktop install creates the user base that Cloud later serves.

### In scope

**Default library location**:
- Move default from `./tiro-library` to platform-appropriate paths:
  - macOS: `~/Library/Application Support/Tiro/`
  - Linux: `~/.local/share/tiro/`
  - Windows: `%APPDATA%\Tiro\`
- `tiro init` writes config with the platform default. Existing installs migrate on next launch with confirmation.
- Backup auto-snapshots go under `<library>/backups/auto/`.

**Desktop packaging** (Tauri recommended):
- Tauri wrapper around the existing FastAPI server. On launch: starts the server on a random free local port, opens a Tauri window pointing at `http://127.0.0.1:<port>`.
- Bundle Python via PyInstaller or PyOxidizer-equivalent; ship a single signed binary per platform.
- App icon, menu bar (preferences, quit), about dialog.
- macOS notarization, Windows code signing (the latter is a separate procurement track).

**Background service management**:
- macOS: `~/Library/LaunchAgents/com.tiro.app.plist` written by `tiro service install`.
- Linux: systemd user unit, `tiro service install` writes `~/.config/systemd/user/tiro.service`.
- Windows: scheduled task or service via `nssm` documented (not bundled).
- `tiro service uninstall`, `tiro service status`, `tiro service logs`.

**Auto-update**:
- Tauri's built-in updater pointed at a JSON manifest hosted on the project's release infrastructure (TBD: GitHub Releases is the obvious default).
- On update: stop service, replace binary, run any migrations (`tiro migrate`), restart service.
- Roll-back on failed startup (preserve previous binary as `tiro.app.previous`).

**First-run onboarding** (the most important UX):
- Welcome → library location → auth password → AI provider choice (Anthropic / OpenAI / local / none) → API key entry → optional email setup → optional Tailscale setup → Chrome extension install link → seed sample articles offer.
- Each step skippable; defaults sane.

**Distribution channels**:
- `uvx tiro` for technical users — already works via `pip install tiro`.
- PyPI release with semver tags.
- Desktop installer per platform from a GitHub Releases page.
- Homebrew tap (`brew install tiro`) as a fast follow.

**Migration framework**:
- `tiro/migrations/` directory with versioned SQL/Python migration files.
- `tiro migrate` CLI; auto-runs on server start with confirmation if schema version differs.
- Migration runs always preceded by an auto-backup snapshot.

### Out of scope

- Mobile native apps (PWA from Phase 3 remains the mobile story).
- Auto-updating the Chrome extension (the Chrome Web Store handles this once published; submission is its own track).
- Multi-platform CI for binary builds — assume manual builds for first release, automate later.

### Dependencies

- All earlier phases.
- A code-signing certificate procurement (macOS Developer ID, Windows EV).
- A release-hosting decision (GitHub Releases vs custom CDN).

### Acceptance criteria

- A non-technical user can download a `.dmg`/`.exe`/`.AppImage`, install Tiro, complete onboarding, and reach the inbox without using a terminal.
- The app survives reboot via the configured service manager.
- Auto-update from version N → N+1 succeeds without data loss.
- Migration framework tested with a forward migration and a rollback drill.

### Test plan

- Manual platform installs (macOS at minimum; Linux + Windows as fast follows).
- Migration tests: take a v0.6 library, install v0.7, confirm data integrity post-migration.
- Service restart test: kill process, confirm restart by launchd/systemd.

### Risks and gotchas

- **Bundling Python is painful**. Allow significant time for the first binary build. PyInstaller is the well-trodden path; PyOxidizer is faster but more brittle.
- **ChromaDB native deps** (RocksDB or similar) may fail to package on Windows. Test early.
- **macOS Gatekeeper / Windows SmartScreen** will block unsigned binaries. Code signing is non-negotiable for public distribution.
- **Library migration risks data loss**. The migration must be a copy-then-confirm-then-remove, never a move.
- **CLAUDE.md warns about port-8000 conflicts**. The Tauri wrapper using a random port avoids this.

---

## Phase 6 — Agent Runtime

**Release target:** `0.8 agent-runtime-beta`
**Relative complexity:** XL
**Goal:** Replace direct prompt calls with an extensible, inspectable library of local agents with replayable traces and a plugin API.

### Why this phase, why now

By 0.7 we have multiple ad-hoc AI features (metadata extractor, digest writer, ingenuity analyst, preference classifier). We are about to add more (highlight summarizer, contradiction detector, reading coach). Continuing as ad-hoc prompts means N feature surfaces with N prompt-update patterns, N retry strategies, N observability stories.

Crucially, this phase is *sixth*, not earlier, because the right abstractions for an agent runtime are only visible after you have shipped enough agents to see the patterns. Building the runtime before shipping notes and RSS risks designing for hypotheticals.

### In scope

**Tiro Agent contract**:
- A typed Python interface for agents:
  ```python
  class TiroAgent(Protocol):
      name: str
      version: str
      inputs: dict[str, type]   # named args
      tools: list[str]          # tools requested
      outputs: type             # pydantic model
      def run(ctx: AgentContext, **kwargs) -> AgentResult: ...
  ```
- `AgentContext` exposes: search, get article, get highlights, write note, create digest, update tags, classify, export — same tools as MCP, intentionally.
- `AgentResult`: outputs + citations (article IDs referenced) + token usage + cost estimate + trace.

**Migrate existing AI features**:
- `MetadataExtractor` agent (replaces direct Haiku call in `processor.py`).
- `DigestWriter` agent (replaces `digest.py` Opus call).
- `IngenuityAnalyst` agent.
- `PreferenceClassifier` agent.
- All preserve current behavior; the migration is a refactor, not a feature change.

**New agents**:
- `HighlightSummarizer` — weekly digest of recent highlights with thematic grouping.
- `ContradictionDetector` — flags articles whose claims contradict each other.
- `ReadingCoach` — surfaces reading habit insights weekly.

**Provider adapters**:
- `AnthropicProvider` (Opus + Haiku).
- `OpenAIProvider` (GPT family + Agents-style workflow support).
- `LocalProvider` (Ollama integration; document recommended local models).
- `MCPProvider` — agent execution delegated to an external MCP-connected assistant.

**Agent run history**:
- New table `agent_runs`: `id, agent_name, agent_version, started_at, completed_at, status, provider, model, input_json, output_json, citations, tokens_in, tokens_out, cost_usd, error`.
- `/agents` view: list runs, filter by agent/date/status, click to view trace, replay button.
- Replay: re-run an agent against the same inputs (useful when prompts or models change).

**Evals**:
- `tiro/evals/` directory with per-agent fixture datasets.
- `tiro evals run [agent]` runs all fixtures, reports pass/fail vs. expected outputs.
- Required for prompt changes: CI gate (manual at first, automated when Phase 5 CI lands).

**Plugin API**:
- Third-party agents installable via `pip install tiro-agent-foo` or dropped into `~/.tiro/plugins/`.
- Plugins declare a manifest (name, version, capabilities, required tools, required API permissions).
- User confirms install; plugins run in the same process with no sandbox initially (sandbox is post-1.0).

### Out of scope

- Multi-agent orchestration (one agent at a time this phase).
- Web-based agent marketplace.
- Sandboxing plugins (deferred until threat model demands it).

### Dependencies

- Phases 0–4 complete.
- AI eval harness foundation from Phase 0 test work.

### Acceptance criteria

- All existing AI features run through the agent runtime with identical user-visible behavior.
- Switching the digest agent from Anthropic to OpenAI requires one config change.
- Every AI call is traceable in `/agents` with full inputs, outputs, and cost.
- Replaying a run with a different model produces a new run record, leaving the original intact.
- An example third-party agent (`tiro-agent-example`) is installable from PyPI and visible in the UI.

### Test plan

- `tests/test_agents.py` — contract conformance, provider switching, error handling.
- `tests/evals/` — fixture-driven evals for each first-party agent.
- Manual: install the example third-party agent, run it, verify trace.

### Risks and gotchas

- **Abstraction risk**: the runtime should be designed *from* the existing agents, not *for* hypothetical ones. Refactor existing first; new agents second.
- **Cost estimation is provider-specific** and tariffs change. Encapsulate per-provider, treat as best-effort.
- **MCPProvider is complex** — defer until the others work.
- **Plugin loading is a security surface**. Document loudly; require explicit user confirmation per plugin.

---

## Phase 7 — Tiro Cloud

**Release target:** `1.0 cloud-beta`
**Relative complexity:** XL
**Goal:** Paid hosted product that adds convenience without compromising local-first ownership.

### Why this phase, why now

Local installs work, packaging is solid, the user base exists. Cloud is the monetization track that funds continued development without compromising the local-first promise (users can keep using Tiro Local forever).

### In scope

**Hosted encrypted sync**:
- Client-side encryption: user holds the key. Server stores ciphertext. Recovery requires the key (with appropriate UX warnings).
- Sync surface: articles, notes, highlights, ratings, VIP, digests, stats history, settings (excluding API keys, which stay local).
- Conflict resolution: last-write-wins per-field for metadata; CRDT for notes; "both versions kept" UI for actual user-edited content.
- Sync transport: HTTPS + signed requests; provider TBD (operator-grade S3-compatible storage is the simplest backend).

**Device pairing**:
- Add device via QR code or short-lived pairing token.
- Per-device sync status, last-sync timestamp.
- Revoke device.

**Hosted web/mobile access**:
- For users who don't run Tiro Local at all: a hosted FastAPI instance serves the same UI against the user's cloud library.
- Read-only by default with optional write access (opt-in, requires key on device).

**Managed AI baseline**:
- Bundled monthly quota of Claude/OpenAI calls.
- BYO-key override always available; usage that exceeds quota falls back to BYO key.
- Cost transparency dashboard.

**Backups, restore points, version history**:
- Server-side immutable backups; client-side `tiro backup` continues to work locally.
- Version history for individual articles and notes (resurrect old versions).

**Shared collections**:
- Read-only share links (encrypted URL fragment as key — server can't decrypt).
- Recipient can subscribe to ongoing updates.
- No public/social discovery — private sharing only.

### Out of scope (this phase)

- Team/library workspaces — explicitly deferred until personal sync is excellent.
- Comments on shared collections.
- Public profiles.

### Dependencies

- All earlier phases.
- A backend infrastructure decision (own hosting vs managed serverless).
- Legal/compliance work for handling user data at rest (terms, privacy policy, GDPR, payment processing).

### Acceptance criteria

- Two devices, one user: changes sync within seconds, with conflict-free behavior for the simple cases and clear UI for the hard cases.
- Disconnecting from cloud preserves all local functionality.
- Encrypted backups verified: drop the user's key, confirm server-side data is unreadable.
- Billing/quota tracking is accurate to within $0.10/month.

### Test plan

- Multi-device sync integration tests (two TestClient instances against a mock sync backend).
- Property-based tests for CRDT merge.
- Pen test of the sync API.
- Manual end-to-end: pair two devices, edit on both, verify convergence.

### Risks and gotchas

- **Encryption-at-rest UX is brutal**. Lose the key, lose the data — communicate this relentlessly.
- **CRDTs for notes** are well-understood (Yjs, Automerge); CRDTs for AI outputs and stats are less so. Default to last-write-wins where conflict is rare.
- **AI quota cost forecasting** is the operational risk — overage exposure has bankrupted infra startups.
- **Compliance scope expands** the moment you store paying users' data. Budget for legal.

---

## Cross-Cutting Tracks

These run alongside the phased work; each is small enough to absorb into the relevant phase but should not be forgotten.

### Telemetry & Observability

- **Local-only structured logs** under `<library>/logs/{date}.jsonl`. Tools: `tiro logs`, `tiro logs --grep`, `tiro logs --since 1h`.
- **Opt-in crash reporting** (Sentry or self-hosted equivalent). Off by default; turning it on is a Settings toggle with a clear privacy explanation. **Never** ship telemetry on by default.
- **Health endpoint** `/healthz` returning version, uptime, store sizes, background task status.
- **`tiro status`** CLI summarizing the same.

Land the local logging in Phase 0; add opt-in telemetry in Phase 5 (when there are many install-base users to debug for).

### AI Eval Harness

- Beyond unit tests: fixture-based evals for AI features. Each fixture is `(input, expected_property)` — expected properties are predicates, not exact match (Opus outputs vary).
- Examples: "digest includes at least 5 articles," "ingenuity score is within ±2 of human label."
- Lives in `tiro/evals/`. Foundation laid in Phase 0; expanded as agents are added; required CI gate in Phase 5 (agent runtime) and beyond.

### Subscription-AI Bridge

- Many users have Claude Pro / ChatGPT Plus / Gemini Advanced subscriptions. They cannot be programmatically driven by Tiro (terms-of-service and product reality).
- Tiro's posture: **expose**, don't automate. MCP server is the primary surface; "handoff" workflows are the secondary surface.
- Handoff: a button that creates a "task packet" (article IDs + highlights + notes + a prompt template), copies it to clipboard, opens the user's preferred assistant.
- Prompt packs: a small library of useful prompts paired with MCP recipes for Claude Code, Claude Desktop, ChatGPT, Gemini, and local assistants.

Land MCP-side improvements in Phase 6 (agent runtime). Land handoff UI in Phase 2 (notes) since highlights/notes are the most valuable content for assistant handoff.

### Rich Media Connectors

Deferred past 1.0. Suggested order when picked up:

1. **PDF connector** with OCR fallback and citation extraction.
2. **YouTube transcript** connector with timestamped sections.
3. **Podcast transcription** connector.

These are high-value but each is a multi-week project with significant ongoing maintenance (API drift, transcription cost, media-specific UX). The product loop is stronger with notes + RSS + sync than with five more connectors.

### Documentation Maintenance

- `CLAUDE.md` should be updated at the end of each phase (the `claude-md-improver` skill is the tool for this).
- `README.md` features section should track the current release.
- `PROJECT_TIRO_SPEC.md` is now historical (hackathon spec); preserve it but mark it as such.
- Add `docs/architecture/` with diagrams once Phase 5 lands (the desktop install will create users who need an architecture doc to debug from).

---

## Out-Of-Scope For This Roadmap

The following are explicit non-goals, called out so planning agents don't drift into them:

- **Team / multi-user accounts.** Single-user remains the design center until at minimum Phase 7.
- **Social / public sharing.** Private remote and private collection sharing only. No public profiles, comments, follow graphs.
- **Automating consumer chat subscriptions.** Tiro does not drive Claude Pro / ChatGPT Plus / Gemini Advanced web UIs.
- **Generic note-taking app.** Notes serve articles; they are not a Notion replacement.
- **In-app web browsing.** Tiro is downstream of save events, not a browser.
- **Building yet another AI chat UI.** Tiro is a reading OS that *uses* AI; it is not a chatbot.
- **Default-on telemetry.** Never.

## Open Strategic Questions

These need product decisions before the relevant phase begins. Listed here so they don't get lost.

1. **Pricing for Tiro Cloud.** Flat monthly with AI bundle, or storage-tier + metered AI? This shapes Phase 7 architecture (especially the AI quota system).
2. **Release-hosting decision.** GitHub Releases is the obvious default for Phase 5, but auto-update at scale eventually wants a CDN. Decide before Phase 5 ships.
3. **Sync backend choice.** Own infra vs Cloudflare R2 vs S3 vs Supabase. Each has different cost/lock-in/encryption-handling profiles.
4. **Mobile native app trigger.** PWA is the plan; the threshold for committing to native iOS/Android is unclear (likely "when users ask for features the PWA cannot deliver" — push notifications? widget? background audio?).
5. **License for paid features.** Tiro is MIT today. Cloud features may want AGPL or a dual-license to discourage hosted-clone competitors.
6. **MCP-vs-native-tool calling** as the canonical tool surface. MCP is more portable; native is lower-latency. Phase 6 should standardize.
7. **Plugin sandboxing approach.** Process isolation? WASM? Trust-the-user-with-warnings? Phase 6 ships without a sandbox; the answer to this question determines when sandboxing becomes mandatory.

---

## Review Verification (from 2026-05-25 review)

The diagnoses in this roadmap were verified against the live codebase on 2026-05-25:

- `tiro/app.py:184` confirmed `allow_origins=["*"]` with `allow_credentials=True`.
- No `DELETE` route found anywhere in `tiro/api/`.
- `marked.parse()` → `innerHTML` confirmed in `tiro/frontend/static/reader.js` and `tiro/frontend/static/app.js`.
- `Path("config.yaml")` hardcoded in `tiro/api/routes_settings.py`.
- IMAP background task creation only in `tiro/app.py` lifespan; no dynamic start/stop from settings route.
- Zero pytest files in the repo.
- `playwright-tests/` contains 39 PNG screenshots, no test code.

Commands previously run during review (kept for reference):

```bash
uv run python -m compileall tiro scripts
uv run tiro --help
uv run tiro export --help
```

These passed at the time of review. Note: `tiro-mcp --help` is not a help-only path; it initializes the MCP server and loads the embedding model. This should be fixed during Phase 0 (small CLI cleanup).
