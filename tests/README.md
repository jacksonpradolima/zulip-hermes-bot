# Tests

The test suite focuses on the behavior that should stay stable as the integration evolves:

- Zulip upload path normalization and traversal rejection.
- Attachment filename safety.
- Generic search query handling and fallback scanning.
- Long Hermes reply chunk reassembly.
- Bot free-response stream matching.
- Catch-up watermark advancement.

Run:

```bash
uv run python -m pytest -q
```
