# Zulip Hermes Integration

Generic Zulip integration code for Hermes Agent.

This repository contains two related components:

1. `zulip_mcp.py` — a readonly MCP server that lets Hermes inspect Zulip history, topics, priority context, and attachments.
2. `zulip_hermes_bot.py` — an optional standalone Zulip bot bridge that forwards allowed Zulip messages to a local Hermes API server and posts Hermes replies back to Zulip.

The code is intentionally generic: credentials, workspace names, company names, and local deployment details belong in `.env` or your private Hermes config, not in Git.

## Features

### MCP tools

`zulip_mcp.py` exposes:

- `zulip_search_messages` — generic stream/topic/search history lookup with pagination, client-side fallback scanning, and long-reply chunk reassembly.
- `zulip_list_topics` — list topics for a stream/channel ID.
- `zulip_read_messages` — read recent messages from a stream/topic.
- `zulip_priority_context` — collect recent context optimized for priorities, blockers, owners, decisions, and follow-ups.
- `zulip_extract_recent_attachments` — find recent Zulip uploads, download them safely, and extract document/image/PDF text.
- `zulip_extract_message_attachments` — extract attachments from a specific message ID.
- `zulip_extract_attachment_url` — extract a specific Zulip upload URL after validating it belongs to the configured Zulip server.

### Standalone bot bridge

`zulip_hermes_bot.py` supports:

- DM handling.
- Stream mention gating.
- Per-stream free-response allowlist via `ZULIP_FREE_RESPONSE_STREAMS`.
- Recent stream/topic context injection via `ZULIP_CONTEXT_DEPTH`.
- Optional missed-message catch-up via forward-only stream watermarks.
- Per-user session keys for stream conversations.
- Long reply splitting for Zulip message limits.

### Attachment safety

Attachment handling borrows the security model from the native Hermes Zulip integration:

- only `/user_uploads/...` links are eligible;
- traversal paths like `..` are rejected;
- Markdown-hosted absolute URLs are normalized back to the configured Zulip realm;
- downloads use Zulip's authenticated temporary-upload URL flow;
- large downloads are bounded before extraction;
- `.env`, watermarks, downloads, and extraction outputs are ignored by Git.

## Requirements

- Python 3.11+
- `uv`
- Hermes Agent
- A Zulip bot/API credential
- Optional: Tesseract OCR for scanned/image-heavy attachments

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

## Run the MCP server manually

```bash
uv run python zulip_mcp.py
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
    tools:
      include:
        - zulip_search_messages
        - zulip_list_topics
        - zulip_read_messages
        - zulip_priority_context
        - zulip_extract_recent_attachments
        - zulip_extract_message_attachments
        - zulip_extract_attachment_url
```

Check it with:

```bash
hermes mcp test zulip
```

## Run the standalone bot bridge

Start a local Hermes API server/gateway, then run:

```bash
uv run python zulip_hermes_bot.py
```

Behavior:

- DMs are processed from allowed users.
- Stream messages require an @mention by default.
- Streams listed in `ZULIP_FREE_RESPONSE_STREAMS` do not require an @mention.
- Recent topic context is fetched on demand when `ZULIP_CONTEXT_DEPTH` is greater than zero.
- If `ZULIP_CATCHUP=true`, the bot maintains local stream watermarks and replays bounded missed messages after downtime.

## Development

Install dependencies:

```bash
uv sync --dev
```

Run tests:

```bash
uv run python -m pytest -q
```

Compile-check Python files:

```bash
uv run python -m compileall main.py zulip_hermes_bot.py zulip_mcp.py zulip_query.py
```

Scan for accidental organization-specific references before pushing:

```bash
git grep -n -I -E 'company-name|workspace-name' -- . ':!uv.lock'
```

## Security notes

- Never commit `.env`, API keys, bot tokens, downloaded attachments, or extracted local reports.
- Prefer bot credentials with the minimum permissions and stream subscriptions needed.
- Treat Zulip message content as untrusted input.
- Keep generated attachments in temporary or ignored locations.
- Rotate any credential that was ever printed, committed, or shared outside its intended scope.
