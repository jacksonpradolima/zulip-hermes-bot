# Installation

## Requirements

- Python 3.11 or newer
- `uv`
- Hermes Agent
- Zulip bot or user API credentials
- Optional: Tesseract OCR for image-heavy attachments

## Clone and install

```bash
git clone https://github.com/jacksonpradolima/zulip-hermes-bot.git
cd zulip-hermes-bot
uv sync --dev --group docs
```

## Configure local credentials

```bash
cp .env.example .env
```

Replace placeholders in `.env`. Never commit this file.

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
