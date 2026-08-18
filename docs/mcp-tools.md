# MCP Tools

The MCP server is implemented in `zulip_hermes.mcp_server` and exposed through the backward-compatible `zulip_mcp.py` wrapper.

## Available tools

| Tool | Purpose |
| --- | --- |
| `zulip_search_messages` | Search history with stream/topic scoping, pagination, fallback scanning, and chunk reassembly. |
| `zulip_list_topics` | List topics in a stream/channel. |
| `zulip_read_messages` | Read recent messages from a stream or topic. |
| `zulip_priority_context` | Build context focused on priorities, blockers, decisions, and follow-ups. |
| `zulip_extract_recent_attachments` | Find and extract recent upload attachments. |
| `zulip_extract_message_attachments` | Extract uploads attached to one message. |
| `zulip_extract_attachment_url` | Extract one validated Zulip upload URL. |

## Run locally

```bash
uv run python zulip_mcp.py
```

or:

```bash
uv run zulip-hermes mcp
```

## Test through Hermes

```bash
hermes mcp test zulip
```

The test should connect over stdio and discover seven tools.
