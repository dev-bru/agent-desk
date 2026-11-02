"""Resume a saved graph after gathering shop facts."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_desk.approver import read_topic
from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.mcp_client import McpTools
from agent_desk.mcp_server import create_server
from agent_desk.messages import parse_message
from agent_desk.resolver import Resolver
from agent_desk.settings import Settings
from agent_desk.shop_db import seed


def main():
    """Rebuild the resolver and finish from its saved next node."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", required=True, help="Use fixed replies and an in-process shop")
    parser.parse_args()
    bus = MemoryBus()
    message = parse_message('{"message_id":"00000000-0000-0000-0000-000000000001","ticket_id":"T-1","type":"ticket.triaged","created_at":"2026-11-02T10:00:00Z","payload":{"customer_id":"C-1","text":"Where is my mug?","order_id":"O-1","channel":"email","category":"order_status","priority":"normal"}}')
    bus.publish("desk.work", "T-1", message.model_dump_json().encode(), {})
    work, = read_topic(bus, "desk.work")
    with TemporaryDirectory(prefix=".pytest-tmp-lesson04-", dir=Path(__file__).resolve().parents[1]) as folder:
        settings = Settings(db_path=Path(folder) / "shop.sqlite", checkpoint_path=Path(folder) / "checkpoints.sqlite")
        seed(settings.db_path)
        tools = McpTools(create_server(settings.db_path))
        first = Resolver(bus, ScriptedModel([{"text": '{"action":"status"}'}]), tools, settings,
                         interrupt_after=["gather"])
        try:
            state = first.run(parse_message(work.value))
            assert state["steps"] == ["plan", "gather"]
            assert state["shipment"]["state"] == "in_transit"
            print("Saved: plan -> gather; next: decide")
        finally:
            first.close()
        model = ScriptedModel([{"text": '{"action":"reply","reply":"Your mug is in transit."}'}])
        second = Resolver(bus, model, tools, settings)
        try:
            state = second.run(message)
            assert state["steps"] == ["plan", "gather", "decide", "reply"]
            assert len(model.requests) == 1 and state["model_calls"] == 2
            assert state["result"]["payload"]["status"] == "resolved"
            print("Resumed: decide -> reply; status: resolved; total model calls: 2")
        finally:
            second.close()


if __name__ == "__main__":
    main()
