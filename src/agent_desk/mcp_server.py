"""Serve the four shop tools through MCP on standard input and output."""

from pathlib import Path
import sqlite3

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from agent_desk.settings import load_settings
from agent_desk.shop_db import ShopDB


def create_server(path: str | Path) -> FastMCP:
    """Make a shop server for one seeded database."""
    server = FastMCP("agent-desk-shop")
    shop = ShopDB(path)

    def call(name, *args):
        """Turn shop errors into MCP error results."""
        try:
            return getattr(shop, name)(*args)
        except ValueError as error:
            raise ToolError(str(error)) from None
        except sqlite3.Error:
            raise ToolError("Shop database is unavailable; run agent-desk seed first") from None

    @server.tool
    def lookup_order(order_id: str) -> dict:
        """Find a seeded order by id, such as O-1 or O-2."""
        return call("lookup_order", order_id)

    @server.tool
    def shipment_status(order_id: str) -> dict:
        """Read the shipment for a seeded order, such as O-1 or O-2."""
        return call("shipment_status", order_id)

    @server.tool
    def refund_policy(category: str) -> dict:
        """Read rules for refund, order_status, shipping, product, or other."""
        return call("refund_policy", category)

    @server.tool
    def issue_refund(order_id: str, amount: float, idempotency_key: str) -> dict:
        """Issue a refund once for the same order, amount, and key."""
        return call("issue_refund", order_id, amount, idempotency_key)

    return server


def main() -> None:
    """Start the shop server with the configured database."""
    create_server(load_settings().db_path).run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
