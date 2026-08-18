# Configuration

Configuration is environment-driven. Copy `.env.example` to `.env` and fill placeholders locally.

## Zulip settings

| Variable | Purpose |
| --- | --- |
| `ZULIP_SITE_URL` | Base URL for the Zulip realm. |
| `ZULIP_BOT_EMAIL` | Bot email used by Zulip API calls. |
| `ZULIP_API_KEY` | Zulip API key for the bot/user. |
| `ZULIP_ALLOWED_USERS` | Comma-separated sender allowlist for the bot bridge. |
| `ZULIP_REQUIRE_MENTION` | Require stream @mentions unless the stream is allowlisted. |
| `ZULIP_FREE_RESPONSE_STREAMS` | Comma-separated stream names or IDs where mentions are not required. |
| `ZULIP_CONTEXT_DEPTH` | Number of recent topic messages included in bot prompts. |
| `ZULIP_CATCHUP` | Enable bounded missed-message catch-up. |
| `ZULIP_CATCHUP_MAX_MESSAGES` | Maximum messages replayed per catch-up query. |
| `ZULIP_DEFAULT_CHANNEL` | Default stream/channel used by priority-context helpers. |
| `ZULIP_DEFAULT_TOPIC` | Default topic used by priority-context helpers. |
| `ZULIP_TIMEZONE` | Timezone used for date-window helpers. |

## Hermes API settings

| Variable | Purpose |
| --- | --- |
| `HERMES_API_URL` | Local Hermes OpenAI-compatible chat-completions endpoint. |
| `HERMES_API_KEY` | Local API key if your Hermes API server requires one. |
| `HERMES_MODEL` | Model name sent to the local Hermes API endpoint. |

## Hermes MCP config

The recommended command keeps the project path explicit and preserves compatibility:

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
```

Test with:

```bash
hermes mcp test zulip
```
