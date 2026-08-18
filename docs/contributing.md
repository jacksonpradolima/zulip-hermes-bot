# Contributing

The canonical contribution guide is available in the repository root:

[Read CONTRIBUTING.md](https://github.com/jacksonpradolima/zulip-hermes-bot/blob/main/CONTRIBUTING.md)

## Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m pytest -q
uv run --group docs mkdocs build --strict
```

Public functions, methods, and classes use NumPy-style docstrings so the API reference stays complete and consistent.
