"""Call shop MCP tools from the synchronous resolver graph."""

import asyncio
import json
from pathlib import Path
import sys

from fastmcp import Client, FastMCP
from fastmcp.client.transports import StdioTransport


class McpError(RuntimeError):
    """Report a failed shop tool or MCP session."""


class McpTools:
    """Use the same MCP calls for an in-process shop or a stdio child."""

    def __init__(self, server: FastMCP | None = None, *, db_path: str | Path = "data/shop.sqlite"):
        """Use an in-process server for tests, or start the configured shop."""
        self.transport = server if server is not None else StdioTransport(
            command=sys.executable, args=["-m", "agent_desk.mcp_server"],
            env={"AGENT_DESK_DB_PATH": str(Path(db_path).resolve())}, keep_alive=False,
        )

    def call(self, name: str, arguments: dict) -> dict:
        """Call a tool and reject its MCP error result."""
        async def invoke():
            """Open one MCP session and read the tool result."""
            async with Client(self.transport, timeout=30) as client:
                result = await client.call_tool(name, arguments, raise_on_error=False)
                text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
                if result.is_error:
                    raise McpError(text)
                data = result.data
                return data if isinstance(data, dict) else json.loads(text)

        # shortcut: Open a session per call; keep a session when demo traffic grows.
        return asyncio.run(invoke())
