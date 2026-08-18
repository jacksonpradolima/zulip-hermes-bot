# Zulip Hermes Integration

[![Code Quality](https://github.com/jacksonpradolima/zulip-hermes-bot/actions/workflows/code_quality.yml/badge.svg)](https://github.com/jacksonpradolima/zulip-hermes-bot/actions/workflows/code_quality.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

Generic Zulip integration components for Hermes Agent.

This repository contains two related runtimes:

1. `zulip_hermes.mcp_server` — a readonly MCP server that lets Hermes inspect Zulip history, topics, priority context, and attachments.
2. `zulip_hermes.bot_bridge` — an optional standalone Zulip bot bridge that forwards allowed Zulip messages to a local Hermes API server and posts Hermes replies back to Zulip.

Root-level scripts remain as compatibility wrappers for existing local configs:

- `zulip_mcp.py`
- `zulip_hermes_bot.py`
- `zulip_query.py`

The code is intentionally generic: credentials, workspace names, company names, and local deployment details belong in `.env` or private Hermes config, not in Git.

---

## Contents

- [Features](#features)
- [Project layout](#project-layout)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [Run the MCP server](#run-the-mcp-server)
- [Run the bot bridge](#run-the-bot-bridge)
- [Development](#development)
- [Security notes](#security-notes)

---

## Features

### MCP tools

`zulip_hermes.mcp_server` exposes:

- `zulip_search_messages` — generic stream/topic/search history lookup with pagination, client-side fallback scanning, and long-reply chunk reassembly.
- `zulip_list_topics` — list topics for a stream/channel ID.
- `zulip_read_messages` — read recent messages from a stream/topic.
- `zulip_priority_context` — collect recent context optimized for priorities, blockers, owners, decisions, and follow-ups.
- `zulip_extract_recent_attachments` — find recent Zulip uploads, download them safely, and extract document/image/PDF text.
- `zulip_extract_message_attachments` — extract attachments from a specific message ID.
- `zulip_extract_attachment_url` — extract a specific Zulip upload URL after validating it belongs to the configured Zulip server.

### Standalone bot bridge

`zulip_hermes.bot_bridge` supports:

- DM handling.
- Stream mention gating.
- Per-stream free-response allowlist via `ZULIP_FREE_RESPONSE_STREAMS`.
- Recent stream/topic context injection via `ZULIP_CONTEXT_DEPTH`.
- Optional missed-message catch-up via forward-only stream watermarks.
- Per-user session keys for stream conversations.
- Long reply splitting for Zulip message limits.

### Attachment safety

Attachment handling follows the security model from the native Hermes Zulip integration:

- only `/user_uploads/...` links are eligible;
- traversal paths like `..` are rejected;
- Markdown-hosted absolute URLs are normalized back to the configured Zulip realm;
- downloads use Zulip's authenticated temporary-upload URL flow;
- large downloads are bounded before extraction;
- `.env`, watermarks, downloads, and extraction outputs are ignored by Git.

---

## Project layout

```text
zulip-hermes-bot/
├── .github/                 # CI, PR template, issue templates
├── docs/                    # Architecture and configuration notes
├── tests/                   # Pytest coverage for core behaviors
├── zulip_hermes/            # Importable package
│   ├── bot_bridge.py        # Zulip listener -> local Hermes API
│   ├── cli.py               # `zulip-hermes` command dispatcher
│   ├── mcp_server.py        # MCP tools exposed to Hermes
│   └── query.py             # Lightweight Zulip query helper
├── zulip_mcp.py             # Backward-compatible MCP wrapper
├── zulip_hermes_bot.py      # Backward-compatible bot wrapper
├── zulip_query.py           # Backward-compatible query wrapper
├── Makefile                 # Common developer commands
├── pyproject.toml           # Package, tooling, and test configuration
└── README.md
```

See `docs/architecture.md` for more detail.

---

## Requirements

- Python 3.11+
- `uv`
- Hermes Agent
- A Zulip bot/API credential
- Optional: Tesseract OCR for scanned/image-heavy attachments

---

## Configuration

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

Fill in the placeholders locally. Do not commit `.env`.

```env
ZULIP_SITE_URL=https://your-zulip-workspace.example.com
ZULIP_BOT_EMAIL=bot@example.com
ZULIP_API_KEY=your-zulip-api-key

ZULIP_ALLOWED_USERS=your-email@example.com
ZULIP_REQUIRE_MENTION=true
ZULIP_FREE_RESPONSE_STREAMS=bot-commands,ai-assistant
ZULIP_CONTEXT_DEPTH=50
ZULIP_CATCHUP=false
ZULIP_CATCHUP_MAX_MESSAGES=100

HERMES_API_URL=http://127.0.0.1:8642/v1/chat/completions
HERMES_API_KEY=change-me
HERMES_MODEL=hermes-agent

ZULIP_DEFAULT_CHANNEL=general
ZULIP_DEFAULT_TOPIC=status
ZULIP_TIMEZONE=America/Sao_Paulo
```

See `docs/configuration.md` for all environment variables.

---

## Run the MCP server

Compatibility entrypoint:

```bash
uv run python zulip_mcp.py
```

Package CLI:

```bash
uv run zulip-hermes mcp
```

Example Hermes MCP config:

```yaml
mcp_servers:
  zulip:
    command: uv
    args:
      - run
      - --project
      - /path/to/zulip-hermes-bot
      - python
      - zulip_mcp.py
    enabled: true
```

Check it with:

```bash
hermes mcp test zulip
```

---

## Run the bot bridge

Start a local Hermes API server/gateway, then run:

```bash
uv run python zulip_hermes_bot.py
```

or:

```bash
uv run zulip-hermes bot
```

Behavior:

- DMs are processed from allowed users.
- Stream messages require an @mention by default.
- Streams listed in `ZULIP_FREE_RESPONSE_STREAMS` do not require an @mention.
- Recent topic context is fetched on demand when `ZULIP_CONTEXT_DEPTH` is greater than zero.
- If `ZULIP_CATCHUP=true`, the bot maintains local stream watermarks and replays bounded missed messages after downtime.

---

## Development

Install dependencies:

```bash
uv sync --dev
```

Run all local checks:

```bash
make check
```

Run individual checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uv run python -m compileall main.py zulip_hermes zulip_mcp.py zulip_hermes_bot.py zulip_query.py
```

---

## Security notes

- Never commit `.env`, API keys, bot tokens, downloaded attachments, or extracted local reports.
- Prefer bot credentials with the minimum permissions and stream subscriptions needed.
- Treat Zulip message content as untrusted input.
- Keep generated attachments in temporary or ignored locations.
- Rotate any credential that was ever printed, committed, or shared outside its intended scope.
