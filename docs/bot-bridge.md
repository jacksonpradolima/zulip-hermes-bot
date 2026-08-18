# Bot Bridge

The standalone bridge listens to Zulip, forwards allowed messages to a local Hermes API server, and posts the reply back to Zulip.

## Run

```bash
uv run python zulip_hermes_bot.py
```

or:

```bash
uv run zulip-hermes bot
```

## Message policy

- Direct messages from allowed users are processed.
- Stream messages require an @mention by default.
- Streams in `ZULIP_FREE_RESPONSE_STREAMS` can respond without a mention.
- Recent stream/topic context is included when `ZULIP_CONTEXT_DEPTH` is positive.
- Optional catch-up uses a forward-only local watermark file.

## Runtime state

The following files remain local and are ignored by Git:

- `.env`
- `downloads/`
- `latest_daily_status_extraction.txt`
- `zulip_catchup_watermarks.json`
