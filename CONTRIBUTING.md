# Contributing

Thanks for improving this Zulip Hermes integration.

## Local setup

```bash
uv sync --dev
```

## Development checks

Run the same checks used by CI:

```bash
make check
```

If Hermes is not installed or the local MCP server is not configured, run the narrower project checks instead:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uv run python -m compileall main.py zulip_hermes zulip_mcp.py zulip_hermes_bot.py zulip_query.py
```

## Secrets and workspace data

Do not commit:

- `.env`
- bot API keys
- local Hermes API keys
- downloaded attachments
- extracted private reports
- company-specific stream names or user names

Use placeholders in docs and examples.

## Commit messages

Use Conventional Commits:

```text
feat: add message search fallback
fix: reject unsafe upload paths
docs: clarify MCP setup
ci: add Python test matrix
```
