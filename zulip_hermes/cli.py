"""Command-line helpers for the Zulip Hermes integration."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the package CLI parser."""
    parser = argparse.ArgumentParser(
        prog="zulip-hermes",
        description="Run Zulip integration components for Hermes Agent.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("mcp", help="Run the Zulip MCP server")
    subcommands.add_parser("bot", help="Run the standalone Zulip bot bridge")
    subcommands.add_parser("query", help="Run the lightweight Zulip query helper")
    return parser


def main() -> None:
    """Dispatch to one of the integration entrypoints."""
    args = build_parser().parse_args()

    if args.command == "mcp":
        from zulip_hermes.mcp_server import mcp

        mcp.run()
        return

    if args.command == "bot":
        from zulip_hermes.bot_bridge import main as bot_main

        bot_main()
        return

    if args.command == "query":
        from zulip_hermes.query import main as query_main

        query_main()
        return

    raise SystemExit(f"Unknown command: {args.command}")
