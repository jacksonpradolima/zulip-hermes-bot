# Architecture

The repository has two runtime surfaces and one shared package.

```text
zulip-hermes-bot/
├── zulip_hermes/          # Importable package
│   ├── bot_bridge.py      # Zulip listener -> local Hermes API -> Zulip reply
│   ├── cli.py             # `zulip-hermes` command dispatcher
│   ├── mcp_server.py      # MCP tools exposed to Hermes
│   └── query.py           # Lightweight API query helper
├── zulip_mcp.py           # Backward-compatible MCP wrapper
├── zulip_hermes_bot.py    # Backward-compatible bot wrapper
└── zulip_query.py         # Backward-compatible query wrapper
```

## MCP server

`zulip_hermes.mcp_server` exposes readonly tools for searching Zulip, reading topics, collecting priority context, and safely extracting attachments. Hermes connects to this process through stdio.

## Bot bridge

`zulip_hermes.bot_bridge` listens for allowed Zulip messages, sends a scoped prompt to the local Hermes API server, and posts the response back into Zulip.

## Compatibility wrappers

The root-level scripts are intentionally preserved. Existing Hermes configs and startup scripts can keep calling `zulip_mcp.py` or `zulip_hermes_bot.py` while new code imports the package modules.

## Data boundaries

Runtime state stays local and ignored by Git:

- `.env`
- `downloads/`
- `latest_daily_status_extraction.txt`
- `zulip_catchup_watermarks.json`
