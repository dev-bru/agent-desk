"""Run triage as a consumer with fixed model replies."""

import argparse

from agent_desk.approver import read_topic
from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.handled import Handled
from agent_desk.messages import parse_message
from agent_desk.simulator import LabeledTicket, ticket_message
from agent_desk.triage import Triage


def main():
    """Classify a ticket and skip its repeated delivery."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", required=True, help="Use the scripted model and memory bus")
    parser.parse_args()
    bus = MemoryBus()
    ticket = LabeledTicket(ticket_id="T-1", customer_id="C-1", order_id="O-1",
                           text="Where is my mug?", channel="email", category="order_status", priority="normal")
    value = ticket_message(ticket).model_dump_json().encode()
    for _ in range(2):
        bus.publish("desk.tickets", "T-1", value, {})
    model = ScriptedModel([{"text": '{"category":"order_status","priority":"normal"}'}])
    store = Handled(":memory:")
    consumer = bus.consume(["desk.tickets"], "triage")
    try:
        assert Triage(bus, model).runner(store).run(consumer) == 2
        work, = read_topic(bus, "desk.work")
        result = parse_message(work.value)
        assert result.payload.category == "order_status" and result.payload.priority == "normal"
        assert len(model.requests) == 1
        print("desk.work: T-1 order_status normal")
        print("2 deliveries; 1 model call; 1 work event")
    finally:
        consumer.close()
        store.close()


if __name__ == "__main__":
    main()
