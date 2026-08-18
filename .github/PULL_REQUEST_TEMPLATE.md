## Summary

- 

## Test plan

- [ ] `uv run python -m pytest -q`
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run python -m compileall main.py zulip_hermes zulip_mcp.py zulip_hermes_bot.py zulip_query.py`

## Security checklist

- [ ] No secrets, tokens, API keys, or real workspace names are committed.
- [ ] `.env` stays untracked.
- [ ] New Zulip API calls keep scope and download limits explicit.
