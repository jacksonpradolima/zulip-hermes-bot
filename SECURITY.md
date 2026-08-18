# Security Policy

## Reporting security issues

Please avoid opening public issues that contain secrets, credentials, private message content, or exploit details. Report sensitive issues privately to the repository owner.

## Secret handling

This project intentionally keeps all credentials outside Git:

- Zulip API keys belong in `.env` or private deployment configuration.
- Hermes local API keys belong in `.env` or private deployment configuration.
- `.env` is ignored by Git; `.env.example` contains placeholders only.
- Downloads, extracted attachments, and catch-up watermarks are ignored by Git.

If a secret is accidentally exposed, rotate it immediately.

## Attachment safety model

Zulip message content is treated as untrusted input. Attachment helpers only accept upload paths under `/user_uploads/...`, reject traversal segments, and resolve downloads through the configured Zulip realm using authenticated API calls.
