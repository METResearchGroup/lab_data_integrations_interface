"""Minimal MCP server used to confirm the MCP client/server flow."""

from mcp.server.fastmcp import FastMCP

server = FastMCP("lab-data-integrations")


@server.tool()
def greet(name: str) -> str:
    """Return a friendly greeting for the provided name."""
    return f"Hello, {name}! The MCP server is working."


if __name__ == "__main__":
    server.run(transport="stdio")
