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

Register the server through the Hermes CLI rather than manually editing Hermes
configuration. Hermes stores the command in the active profile and launches the
server on demand; it does not copy this repository into a Hermes directory.
Replace `<ABSOLUTE_PROJECT_PATH>` with the stable local checkout path:

```bash
hermes mcp add zulip --command uv --args run --project <ABSOLUTE_PROJECT_PATH> python <ABSOLUTE_PROJECT_PATH>/zulip_mcp.py
```

The MCP server resolves `.env` from its project directory, so credentials stay
in the ignored project-local file rather than in the Hermes MCP command. Test
the setup with:

```bash
hermes mcp test zulip
```
