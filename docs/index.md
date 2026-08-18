# Zulip Hermes Integration

[![Code Quality](https://github.com/jacksonpradolima/zulip-hermes-bot/actions/workflows/code_quality.yml/badge.svg)](https://github.com/jacksonpradolima/zulip-hermes-bot/actions/workflows/code_quality.yml)
[![Documentation](https://github.com/jacksonpradolima/zulip-hermes-bot/actions/workflows/docs.yml/badge.svg)](https://github.com/jacksonpradolima/zulip-hermes-bot/actions/workflows/docs.yml)

A generic, secret-safe Zulip integration for Hermes Agent.

<div class="grid cards" markdown>

-   :material-tools:{ .lg .middle } **Readonly MCP tools**

    ---

    Search messages, inspect topics, collect priority context, and extract attachments.

    [:octicons-arrow-right-24: MCP tools](mcp-tools.md)

-   :material-robot:{ .lg .middle } **Standalone bot bridge**

    ---

    Forward allowed Zulip messages to a local Hermes API and post responses back to Zulip.

    [:octicons-arrow-right-24: Bot bridge](bot-bridge.md)

-   :material-shield-lock:{ .lg .middle } **Secure by default**

    ---

    Keep credentials local, validate upload paths, bound downloads, and ignore runtime artifacts.

    [:octicons-arrow-right-24: Security](security.md)

-   :material-code-braces:{ .lg .middle } **Documented Python API**

    ---

    Browse automatically generated API documentation from NumPy-style docstrings.

    [:octicons-arrow-right-24: API reference](api/mcp-server.md)

</div>

## Components

```text
Zulip messages
      │
      ├── readonly tools ──> zulip_hermes.mcp_server ──> Hermes MCP
      │
      └── bot events ─────> zulip_hermes.bot_bridge ──> Hermes local API
```

## Quick start

```bash
uv sync --dev --group docs
cp .env.example .env
uv run python zulip_mcp.py
```

Verify the configured MCP server:

```bash
hermes mcp test zulip
```

## Compatibility

Existing local scripts can keep using the root entrypoints:

- `zulip_mcp.py`
- `zulip_hermes_bot.py`
- `zulip_query.py`

New code can import the `zulip_hermes` package directly.
