"""Call the real MCP server in process without sockets."""

import asyncio
import sqlite3

from fastmcp import Client

from agent_desk.mcp_server import create_server
from agent_desk.shop_db import seed


def test_shop_tools(tmp_path):
    """Known ids return seeded data and repeated refunds return one row."""
    path = tmp_path / "shop.sqlite"
    seed(path)

    async def check():
        async with Client(create_server(path)) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools} == {
                "lookup_order", "shipment_status", "refund_policy", "issue_refund",
            }
            for name, args, field, expected in [
                ("lookup_order", {"order_id": "O-1"}, "total", 30),
                ("shipment_status", {"order_id": "O-1"}, "state", "in_transit"),
                ("refund_policy", {"category": "refund"}, "max_days", 30),
            ]:
                result = await client.call_tool(name, args)
                assert not result.is_error
                assert result.data[field] == expected
            args = {"order_id": "O-1", "amount": 10, "idempotency_key": "T-1:refund"}
            first = await client.call_tool("issue_refund", args)
            assert (await client.call_tool("issue_refund", args)).data == first.data

    asyncio.run(check())
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (1,)


def test_errors_are_mcp_results(tmp_path):
    """Missing ids and invalid refunds return isError through MCP."""
    path = tmp_path / "shop.sqlite"
    seed(path)

    async def check():
        async with Client(create_server(path)) as client:
            for name, args in [
                ("lookup_order", {"order_id": "missing"}),
                ("shipment_status", {"order_id": "missing"}),
                ("refund_policy", {"category": "missing"}),
                ("issue_refund", {"order_id": "missing", "amount": 1, "idempotency_key": "x"}),
            ]:
                result = await client.call_tool(name, args, raise_on_error=False)
                assert result.is_error
                assert "missing" in result.content[0].text
            result = await client.call_tool("issue_refund", {
                "order_id": "O-1", "amount": -1, "idempotency_key": "x",
            }, raise_on_error=False)
            assert result.is_error
            assert "amount" in result.content[0].text

    asyncio.run(check())
