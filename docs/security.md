# Security

The canonical security policy is available in the repository root:

[Read SECURITY.md](https://github.com/jacksonpradolima/zulip-hermes-bot/blob/main/SECURITY.md)

## Core rules

- Never commit credentials or private message exports.
- Treat Zulip message content as untrusted input.
- Only accept validated `/user_uploads/...` paths for attachment extraction.
- Keep download and OCR limits explicit.
- Rotate any credential that was exposed outside its intended scope.
