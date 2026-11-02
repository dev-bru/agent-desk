"""Check resolver paths, MCP calls, durable resume, and result deduplication."""

import json
import sqlite3

import pytest

from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.handled import Handled
from agent_desk.mcp_client import McpError, McpTools
from agent_desk.mcp_server import create_server
from agent_desk.messages import parse_message
from agent_desk.resolver import Resolver
from agent_desk.settings import Settings
from agent_desk.shop_db import seed


def work(category="order_status", order="O-1", customer="C-1", ticket="T-1"):
    """Make one triaged ticket for the graph."""
    return parse_message(json.dumps({
        "message_id": "00000000-0000-0000-0000-000000000001", "ticket_id": ticket,
        "type": "ticket.triaged", "created_at": "2026-11-02T10:00:00Z", "payload": {
            "customer_id": customer, "order_id": order, "text": "Help with my order", "channel": "email",
            "category": category, "priority": "normal",
        },
    }))


@pytest.fixture
def shop(tmp_path):
    """Seed a temporary shop and use its actual in-process MCP server."""
    settings = Settings(db_path=tmp_path / "shop.sqlite", checkpoint_path=tmp_path / "checkpoints.sqlite")
    seed(settings.db_path)
    return settings, McpTools(create_server(settings.db_path))


def test_status_reaches_reply(shop):
    """A status ticket reads MCP facts and replies without approval or refund."""
    settings, tools = shop
    model = ScriptedModel([{"text": '{"action":"status"}'},
                           {"text": '{"action":"reply","reply":"Your mug is in transit."}'}])
    resolver = Resolver(MemoryBus(), model, tools, settings)
    try:
        state = resolver.run(work())
        assert state["steps"] == ["plan", "gather", "decide", "reply"]
        assert state["shipment"]["state"] == "in_transit"
        assert state["result"]["payload"]["status"] == "resolved"
        assert "in_transit" in model.requests[1]["messages"][-1]["content"]
        assert state["model_calls"] == 2
    finally:
        resolver.close()


@pytest.mark.parametrize("amount", [30.0, 50.0])
def test_small_refund_path(shop, amount):
    """Refunds below and at the limit go straight from decide to act to reply."""
    settings, tools = shop
    model = ScriptedModel([{"text": '{"action":"refund"}'},
                           {"text": json.dumps({"action": "refund", "amount": amount})}])
    resolver = Resolver(MemoryBus(), model, tools, settings)
    try:
        state = resolver.run(work("refund", "O-2", "C-2"))
        assert state["steps"] == ["plan", "gather", "decide", "act", "reply"]
        assert state["result"]["payload"]["refund_amount"] == amount
        assert state["result"]["payload"]["status"] == "refunded"
        assert f"{amount:.2f}" in state["result"]["payload"]["reply"]
    finally:
        resolver.close()


def test_default_step_limit(shop):
    """Repeated requests for facts stop at eight model calls with a clear result."""
    settings, tools = shop
    model = ScriptedModel([{"text": '{"action":"status"}'}] + [{"text": '{"action":"gather"}'}] * 7)
    resolver = Resolver(MemoryBus(), model, tools, settings)
    try:
        state = resolver.run(work())
        assert len(model.requests) == state["model_calls"] == 8
        assert state["status"] == "escalated"
        assert "step limit of 8 model calls" in state["result"]["payload"]["reply"]
        assert state["steps"][-1] == "reply"
    finally:
        resolver.close()


def test_restart_after_gather(shop, monkeypatch):
    """Rebuilding from a saved checkpoint starts at decide and does not repeat MCP reads."""
    settings, tools = shop
    calls = []
    original = tools.call

    def record(name, arguments):
        """Count real MCP calls before and after the restart."""
        calls.append(name)
        return original(name, arguments)

    monkeypatch.setattr(tools, "call", record)
    first = Resolver(MemoryBus(), ScriptedModel([{"text": '{"action":"status"}'}]), tools, settings,
                     interrupt_after=["gather"])
    try:
        state = first.run(work())
        assert state["steps"] == ["plan", "gather"]
        assert first.graph.get_state({"configurable": {"thread_id": "T-1"}}).next == ("decide",)
    finally:
        first.close()
    before = calls.copy()
    model = ScriptedModel([{"text": '{"action":"reply","reply":"Your mug is in transit."}'}])
    second = Resolver(MemoryBus(), model, tools, settings)
    try:
        state = second.run(work())
        assert calls == before == ["lookup_order", "shipment_status", "refund_policy"]
        assert state["steps"] == ["plan", "gather", "decide", "reply"]
        assert state["model_calls"] == 2
    finally:
        second.close()


def test_result_once_after_restart_and_commit_failure(shop, tmp_path):
    """A failed input commit and duplicate work do not repeat the result or refund."""
    settings, tools = shop
    bus = MemoryBus()
    message = work("refund")
    model = ScriptedModel([{"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":30}'}])
    path = tmp_path / "handled.sqlite"
    store = Handled(path)
    resolver = Resolver(bus, model, tools, settings)
    bus.publish("desk.work", "T-1", message.model_dump_json().encode(), {"idempotency-key": b"T-1:resolve"})
    subscription = bus.consume(["desk.work"], "resolver")

    class FailedCommit:
        """Fail the broker acknowledgement after the result was saved."""

        def commit(self, record):
            """Leave the work record unacknowledged."""
            raise OSError("Commit failed")

    try:
        with pytest.raises(OSError, match="Commit failed"):
            resolver.runner(store).process(subscription.poll(), FailedCommit())
    finally:
        subscription.close()
        store.close()
        resolver.close()
    store = Handled(path)
    resolver = Resolver(bus, ScriptedModel([]), tools, settings)
    subscription = bus.consume(["desk.work"], "resolver")
    try:
        bus.publish("desk.work", "T-1", message.model_dump_json().encode(), {})
        assert resolver.runner(store).run(subscription) == 2
        results = bus.consume(["desk.results"], "check")
        record = results.poll()
        assert record.headers["idempotency-key"] == b"T-1:resolve"
        assert parse_message(record.value).payload.status == "refunded"
        results.commit(record)
        assert results.poll() is None
        results.close()
        with sqlite3.connect(settings.db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (1,)
    finally:
        subscription.close()
        store.close()
        resolver.close()


def test_large_refund_pauses(shop):
    """A large refund cannot reach the refund tool before approval is implemented."""
    settings, tools = shop
    model = ScriptedModel([{"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":75}'}])
    resolver = Resolver(MemoryBus(), model, tools, settings)
    try:
        state = resolver.run(work("refund", "O-2", "C-2"))
        assert "result" not in state
        saved = resolver.graph.get_state({"configurable": {"thread_id": "T-1"}})
        assert saved.next == ("await_approval",)
        assert saved.interrupts[0].value["amount"] == 75
        with sqlite3.connect(settings.db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (0,)
    finally:
        resolver.close()


def test_mcp_error_and_wrong_owner(shop):
    """Tool errors and another customer's order cannot become successful refunds."""
    settings, tools = shop
    with pytest.raises(McpError, match="missing"):
        tools.call("lookup_order", {"order_id": "missing"})
    resolver = Resolver(MemoryBus(), ScriptedModel([{"text": '{"action":"refund"}'}]), tools, settings)
    try:
        with pytest.raises(ValueError, match="customer_id"):
            resolver.run(work("refund", "O-2", "C-1"))
    finally:
        resolver.close()


def test_publish_failure_reuses_finished_checkpoint(shop, tmp_path, monkeypatch):
    """Retry a failed publish without repeating the model or refund tool."""
    settings, tools = shop
    bus = MemoryBus()
    model = ScriptedModel([{"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":30}'}])
    resolver = Resolver(bus, model, tools, settings)
    store = Handled(tmp_path / "handled.sqlite")
    message = work("refund")
    bus.publish("desk.work", "T-1", message.model_dump_json().encode(), {})
    publish = bus.publish
    attempts = []

    def fail_once(topic, key, value, headers):
        """Fail before the first result reaches the bus."""
        attempts.append(value)
        if len(attempts) == 1:
            raise OSError("Broker is down")
        publish(topic, key, value, headers)

    monkeypatch.setattr(bus, "publish", fail_once)
    subscription = bus.consume(["desk.work"], "resolver")
    try:
        resolver.runner(store, max_attempts=2, sleep=lambda delay: None).run(subscription)
        assert len(attempts) == 2
        assert attempts[0] == attempts[1]
        assert len(model.requests) == 2
        with sqlite3.connect(settings.db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (1,)
        results = bus.consume(["desk.results"], "check")
        record = results.poll()
        assert parse_message(record.value).payload.status == "refunded"
        results.commit(record)
        assert results.poll() is None
        results.close()
    finally:
        subscription.close()
        store.close()
        resolver.close()


def test_native_stdio_shop(tmp_path):
    """The native Python MCP child serves consecutive calls without a network service."""
    path = tmp_path / "shop.sqlite"
    seed(path)
    tools = McpTools(db_path=path)
    assert tools.call("lookup_order", {"order_id": "O-1"})["total"] == 30
    assert tools.call("shipment_status", {"order_id": "O-1"})["state"] == "in_transit"
