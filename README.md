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
git clone https://github.com/yourusername/project-tiro.git
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

## License

MIT
