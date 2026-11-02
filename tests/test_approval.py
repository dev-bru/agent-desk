"""Prove that human pauses survive restarts and repeated delivery."""

import sqlite3
from uuid import uuid4

import pytest

from agent_desk.approver import decide, pending, read_topic
from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.handled import Handled
from agent_desk.messages import parse_message
from agent_desk.resolver import Resolver
from agent_desk.triage import Triage
from test_resolver import shop, work


def drain(bus, topic, runner, group):
    """Handle all records in a temporary subscription."""
    subscription = bus.consume([topic], group)
    try:
        return runner.run(subscription)
    finally:
        subscription.close()


@pytest.mark.parametrize("approved", [True, False])
def test_restart_and_duplicate_decision(shop, tmp_path, approved):
    """Other tickets finish while approval waits, then one decision completes the refund."""
    settings, tools = shop
    bus = MemoryBus()
    store = Handled(tmp_path / "handled.sqlite")
    model = ScriptedModel([
        {"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":75}'},
        {"text": '{"action":"status"}'}, {"text": '{"action":"reply","reply":"In transit"}'},
    ])
    resolver = Resolver(bus, model, tools, settings)
    for message in [work("refund", "O-2", "C-2"), work(ticket="T-2")]:
        bus.publish("desk.work", message.ticket_id, message.model_dump_json().encode(), {})
    try:
        assert drain(bus, "desk.work", resolver.runner(store), "resolver") == 2
        assert [item.ticket_id for item in pending(bus)] == ["T-1"]
        assert parse_message(read_topic(bus, "desk.results")[0].value).ticket_id == "T-2"
    finally:
        resolver.close()
    resolver = Resolver(bus, ScriptedModel([]), tools, settings)
    try:
        message = decide(bus, "T-1", approved, "Sam", "Outside policy")
        duplicate = message.model_copy(update={
            "message_id": uuid4(), "payload": message.payload.model_copy(update={"approved": not approved}),
        })
        bus.publish("desk.approvals.decisions", "T-1", duplicate.model_dump_json().encode(), {})
        assert drain(bus, "desk.approvals.decisions", resolver.decision_runner(store), "decisions") == 2
        results = [parse_message(record.value) for record in read_topic(bus, "desk.results")]
        assert len(results) == 2
        assert results[-1].payload.status == ("refunded" if approved else "declined")
        assert ("75.00" if approved else "Outside policy") in results[-1].payload.reply
        with sqlite3.connect(settings.db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (int(approved),)
        assert pending(bus) == []
    finally:
        resolver.close()
        store.close()


def test_triage_crash_after_publish_is_absorbed(shop, tmp_path):
    """A crash before saving the triage key can publish twice but refunds once."""
    settings, tools = shop
    bus = MemoryBus()
    store = Handled(tmp_path / "handled.sqlite")
    triage = Triage(bus, ScriptedModel([{"text": '{"category":"refund","priority":"normal"}'}] * 2))
    message = work("refund")
    created = message.model_dump(mode="json")
    created["type"] = "ticket.created"
    del created["payload"]["category"], created["payload"]["priority"]
    from agent_desk.messages import TicketCreatedEnvelope
    created = TicketCreatedEnvelope.model_validate(created)
    bus.publish("desk.tickets", created.ticket_id, created.model_dump_json().encode(), {})
    subscription = bus.consume(["desk.tickets"], "triage")
    subscription.poll()

    def crash(connection):
        """Stop after the real publish and before the handled key write."""
        triage.handle(created, connection)
        raise KeyboardInterrupt("Process stopped")

    with pytest.raises(KeyboardInterrupt):
        store.run("triage", "T-1:triage", crash)
    subscription.close()
    drain(bus, "desk.tickets", triage.runner(store), "triage")
    assert len(read_topic(bus, "desk.work")) == 2
    resolver = Resolver(bus, ScriptedModel([
        {"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":30}'},
    ]), tools, settings)
    try:
        assert drain(bus, "desk.work", resolver.runner(store), "resolver") == 2
        assert len(read_topic(bus, "desk.results")) == 1
        with sqlite3.connect(settings.db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (1,)
    finally:
        resolver.close()
        store.close()


def test_decision_publish_retry(shop, tmp_path, monkeypatch):
    """A failed result publish resumes from the finished checkpoint without refunding again."""
    settings, tools = shop
    bus = MemoryBus()
    store = Handled(tmp_path / "handled.sqlite")
    resolver = Resolver(bus, ScriptedModel([
        {"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":75}'},
    ]), tools, settings)
    try:
        resolver.handle(work("refund", "O-2", "C-2"), store.connection)
        decide(bus, "T-1", True, "Sam")
        publish = bus.publish
        calls = []

        def fail_once(topic, key, value, headers):
            """Fail before the first result publish."""
            calls.append(value)
            if len(calls) == 1:
                raise OSError("Unavailable")
            publish(topic, key, value, headers)

        monkeypatch.setattr(bus, "publish", fail_once)
        drain(bus, "desk.approvals.decisions",
              resolver.decision_runner(store, sleep=lambda delay: None), "decisions")
        assert len(calls) == 2 and calls[0] == calls[1]
        assert len(read_topic(bus, "desk.results")) == 1
        with sqlite3.connect(settings.db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM refunds").fetchone() == (1,)
    finally:
        resolver.close()
        store.close()
