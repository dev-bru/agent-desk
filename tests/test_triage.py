"""Check triage output, repair, and durable duplicate handling."""

import json

import pytest

from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.handled import Handled
from agent_desk.messages import parse_message
from agent_desk.model import ModelError
from agent_desk.triage import Triage


def ticket():
    """Make one ticket for a seeded shop order."""
    return parse_message(json.dumps({
        "message_id": "00000000-0000-0000-0000-000000000001", "ticket_id": "T-1",
        "type": "ticket.created", "created_at": "2026-11-02T10:00:00Z",
        "payload": {"customer_id": "C-1", "order_id": "O-1", "text": "Where is my mug?", "channel": "email"},
    }))


def test_triage_and_restart(tmp_path):
    """A duplicate ticket uses one model reply and publishes one work event."""
    bus = MemoryBus()
    model = ScriptedModel([{"text": '{"category":"order_status","priority":"high"}'}])
    triage = Triage(bus, model)
    path = tmp_path / "handled.sqlite"
    for _ in range(2):
        bus.publish("desk.tickets", "T-1", ticket().model_dump_json().encode(), {})
        store = Handled(path)
        subscription = bus.consume(["desk.tickets"], "triage")
        triage.runner(store).run(subscription)
        subscription.close()
        store.close()
    subscription = bus.consume(["desk.work"], "check")
    record = subscription.poll()
    work = parse_message(record.value)
    assert work.payload.category == "order_status"
    assert work.payload.priority == "high"
    assert work.payload.text == ticket().payload.text
    assert record.headers["idempotency-key"] == b"T-1:resolve"
    subscription.commit(record)
    assert subscription.poll() is None
    subscription.close()
    assert len(model.requests) == 1


@pytest.mark.parametrize("first", ["broken", '{"category":"unknown","priority":"normal"}',
                                   '{"category":"refund"}'])
def test_repair_once(first):
    """One repair can turn bad JSON or a bad field into valid work."""
    model = ScriptedModel([{"text": first}, {"text": '{"category":"shipping","priority":"normal"}'}])
    Triage(MemoryBus(), model).handle(ticket(), None)
    assert len(model.requests) == 2
    assert "Repair" in model.requests[1]["messages"][-1]["content"]
    assert len(model.requests[0]["messages"]) == 2


def test_failed_repair_raises():
    """Two invalid replies raise for the runner to retry or dead-letter."""
    model = ScriptedModel([{"text": "broken"}, {"text": "still broken"}])
    bus = MemoryBus()
    with pytest.raises(ModelError, match="one repair"):
        Triage(bus, model).handle(ticket(), None)
    assert len(model.requests) == 2
    assert bus.consume(["desk.work"], "check").poll() is None
