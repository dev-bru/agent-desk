"""Pause a large refund, rebuild the resolver, and approve it."""

import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from agent_desk.approver import decide, pending, read_topic
from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.handled import Handled
from agent_desk.mcp_client import McpTools
from agent_desk.mcp_server import create_server
from agent_desk.messages import parse_message
from agent_desk.resolver import Resolver
from agent_desk.settings import Settings
from agent_desk.shop_db import seed


def main():
    """Send a decision to a saved graph and refund once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", required=True, help="Use fixed replies and an in-process shop")
    parser.parse_args()
    bus = MemoryBus()
    value = b'{"message_id":"00000000-0000-0000-0000-000000000001","ticket_id":"T-1","type":"ticket.triaged","created_at":"2026-11-02T10:00:00Z","payload":{"customer_id":"C-2","text":"Please refund my order","order_id":"O-2","channel":"email","category":"refund","priority":"normal"}}'
    bus.publish("desk.work", "T-1", value, {})
    with TemporaryDirectory(prefix=".pytest-tmp-lesson05-", dir=Path(__file__).resolve().parents[1]) as folder:
        settings = Settings(db_path=Path(folder) / "shop.sqlite", checkpoint_path=Path(folder) / "checkpoints.sqlite")
        seed(settings.db_path)
        tools = McpTools(create_server(settings.db_path))
        store = Handled(Path(folder) / "handled.sqlite")
        model = ScriptedModel([{"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":75}'}])
        first = Resolver(bus, model, tools, settings)
        consumer = bus.consume(["desk.work"], "resolver")
        try:
            assert first.runner(store).run(consumer) == 1
            request, = pending(bus)
            assert request.payload.amount == 75 and request.payload.limit == 50
            assert read_topic(bus, "desk.results") == []
            print("Pending: T-1 refund 75.00 above limit 50.00; no result yet")
        finally:
            first.close()
            consumer.close()
            store.close()
        second = Resolver(bus, ScriptedModel([]), tools, settings)
        store = Handled(Path(folder) / "handled.sqlite")
        consumer = bus.consume(["desk.approvals.decisions"], "decisions")
        try:
            decision = decide(bus, "T-1", True, "Sam", "Checked order")
            bus.publish("desk.approvals.decisions", "T-1", decision.model_dump_json().encode(), {})
            assert second.decision_runner(store).run(consumer) == 2
            result, = read_topic(bus, "desk.results")
            assert parse_message(result.value).payload.status == "refunded"
            with closing(sqlite3.connect(settings.db_path)) as connection:
                assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (1,)
            assert pending(bus) == []
            print("Approved after restart: refunded 75.00; 1 refund; 1 result despite duplicate decision")
        finally:
            consumer.close()
            store.close()
            second.close()


if __name__ == "__main__":
    main()
