"""Backward-compatible entrypoint for the Zulip Hermes MCP server."""

from zulip_hermes.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
