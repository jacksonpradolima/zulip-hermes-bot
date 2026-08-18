# Installation

## Requirements

- Python 3.11 or newer
- `uv`
- Hermes Agent
- Zulip bot or user API credentials
- Optional: Tesseract OCR for image-heavy attachments

## Plug into Hermes

Hermes runs this repository as a local stdio MCP server. It does not copy the
project into its own directory or install it as a skill; the Hermes profile
only stores a command that points to this stable local checkout.

Clone the project into a permanent local directory:

```bash
git clone https://github.com/jacksonpradolima/zulip-hermes-bot.git
cd zulip-hermes-bot
uv sync --frozen
```

## Configure local credentials

```bash
cp .env.example .env
```

Replace placeholders in `.env`. Never commit this file.

Register the MCP server with Hermes. Replace `<ABSOLUTE_PROJECT_PATH>` with
the absolute path of this checkout. On Windows use forward slashes, for example
`C:/Users/alice/tools/zulip-hermes-bot`:

```bash
hermes mcp add zulip --command uv --args run --project <ABSOLUTE_PROJECT_PATH> python <ABSOLUTE_PROJECT_PATH>/zulip_mcp.py
hermes mcp test zulip
```

The test should discover seven readonly Zulip tools. Start a new Hermes session
or run `/reset` after registering the server so the current chat sees its tools.

For later updates, run `git pull --ff-only`, `uv sync --frozen`, and
`hermes mcp test zulip` from this checkout. No second `hermes mcp add` is needed.

## Validate the project

```bash
make test
make lint
make compile
```

## Build the documentation

```bash
uv run --group docs mkdocs build --strict
```

The generated site is written to `site/`, which is ignored by Git.
