# Changelog

All notable changes to this project will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and commit messages follow Conventional Commits.

## [0.2.0] - 2026-08-17

### Added

- Packaged `zulip_hermes` module layout.
- Generic `zulip-hermes` CLI with `mcp`, `bot`, and `query` subcommands.
- `zulip_search_messages` MCP tool with stream/topic filtering, pagination, fallback scanning, and long-message chunk reassembly.
- Optional free-response streams for the bot bridge.
- Optional catch-up watermarks for missed stream messages.
- Tests for PR-derived search, attachment, free-response, and watermark behavior.
- GitHub Actions code-quality workflow.
- Contributor, security, and development docs.

### Changed

- Kept root scripts as backward-compatible wrappers for existing Hermes MCP config and startup scripts.
- Reworked docs and defaults to remain generic and secret-safe.

## [0.1.0] - 2026-08-17

### Added

- Initial generic Zulip MCP server and standalone bot bridge.
