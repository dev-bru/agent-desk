"""Check retries, input commits, poison handling, and replay offline."""

import json
import logging

import pytest

from agent_desk.bus import MemoryBus
from agent_desk.cli import main
from agent_desk.handled import Handled
from agent_desk.messages import BadMessage
from agent_desk.runner import DEAD_LETTER_TOPIC, Runner, list_dead_letters, replay


def publish(bus, ticket="T-1", value=None):
    """Publish a valid ticket unless a poison body is supplied."""
    if value is None:
        value = json.dumps({"message_id": "00000000-0000-0000-0000-000000000001", "ticket_id": ticket, "type": "ticket.created", "created_at": "2026-11-02T10:00:00Z", "payload": {"customer_id": "C-1", "text": "Help", "channel": "email"}}).encode()
    bus.publish("desk.tickets", ticket, value, {"traceparent": b"demo", "idempotency-key": f"{ticket}:triage".encode()})


def test_duplicate_and_commit_failure(tmp_path):
    """Redelivery after a failed commit does not repeat database work."""
    bus = MemoryBus()
    publish(bus)
    store = Handled(tmp_path / "handled.sqlite")
    calls = []
    runner = Runner(bus, store, "triage", "triage", lambda message, connection: calls.append(message.ticket_id))
    subscription = bus.consume(["desk.tickets"], "triage")

    class FailedCommit:
        """Simulate a broker failure after the handler returns."""

        def commit(self, record):
            """Fail the input acknowledgement."""
            raise OSError("Commit failed")

    with pytest.raises(OSError):
        runner.process(subscription.poll(), FailedCommit())
    subscription.close()
    store.close()
    store = Handled(tmp_path / "handled.sqlite")
    runner.handled = store
    publish(bus)
    assert runner.run(bus.consume(["desk.tickets"], "triage")) == 2
    assert calls == ["T-1"]
    assert list_dead_letters(bus) == []
    store.close()


def test_retries_headers_backoff_and_logs(tmp_path, caplog):
    """Two failed attempts roll back and sleep within the stated bounds."""
    bus = MemoryBus()
    publish(bus)
    subscription = bus.consume(["desk.tickets"], "triage")
    record = subscription.poll()
    store = Handled(tmp_path / "handled.sqlite")
    store.connection.execute("CREATE TABLE effects (value TEXT)")
    attempts, delays = [], []

    def handler(message, connection):
        """Fail twice after a database write, then succeed."""
        attempts.append(record.headers["attempt"])
        connection.execute("INSERT INTO effects VALUES ('done')")
        if len(attempts) < 3:
            raise OSError("Temporary failure")

    def jitter(low, high):
        """Return the upper jitter bound without using randomness."""
        assert (low, high) == (0, 0.2)
        return high

    runner = Runner(bus, store, "triage", "triage", handler, backoff_base_s=2, sleep=delays.append, jitter=jitter)
    with caplog.at_level(logging.INFO):
        runner.process(record, subscription)
    assert attempts == [b"1", b"2", b"3"]
    assert delays == [2.2, 4.2]
    assert all(f"attempt={attempt}" in caplog.text for attempt in (1, 2, 3))
    assert store.connection.execute("SELECT * FROM effects").fetchall() == [("done",)]
    assert subscription.poll() is None
    store.close()


@pytest.mark.parametrize("failure,expected_calls,expected_attempts", [("poison", 0, b"0"), ("schema", 1, b"1"), ("transient", 3, b"3")])
def test_dead_letter_then_next_and_replay(tmp_path, failure, expected_calls, expected_attempts, capsys):
    """Poison and exhausted failures do not stop the next ticket."""
    bus = MemoryBus()
    publish(bus, value=b"broken" if failure == "poison" else None)
    publish(bus, "T-2")
    store = Handled(tmp_path / "handled.sqlite")
    calls, delays = [], []

    def handler(message, connection):
        """Fail the first ticket and accept the next one."""
        calls.append(message.ticket_id)
        if message.ticket_id == "T-1":
            if failure == "schema":
                raise BadMessage("Invalid field: text")
            raise OSError("Temporary failure")

    runner = Runner(bus, store, "triage", "triage", handler, sleep=delays.append)
    assert runner.run(bus.consume(["desk.tickets"], "triage")) == 2
    assert calls.count("T-1") == expected_calls
    assert calls.count("T-2") == 1
    assert len(delays) == (2 if failure == "transient" else 0)
    dead, = list_dead_letters(bus)
    assert dead.topic == DEAD_LETTER_TOPIC
    assert dead.headers["dlq-attempts"] == expected_attempts
    assert dead.headers["dlq-source-topic"] == b"desk.tickets"
    assert dead.headers["traceparent"] == b"demo"
    assert dead.headers["dlq-reason"]
    assert main(["dlq", "list"], bus=bus) == 0
    assert "T-1" in capsys.readouterr().out
    assert main(["dlq", "replay", str(dead.offset)], bus=bus) == 0
    replayed = bus.consume(["desk.tickets"], "triage")
    record = replayed.poll()
    assert record.value == dead.value
    assert record.headers == {"traceparent": b"demo", "idempotency-key": b"T-1:triage"}
    if failure != "poison":
        runner.handler = lambda message, connection: calls.append(message.ticket_id)
        runner.process(record, replayed)
        assert calls.count("T-1") == expected_calls + 1
    replayed.close()
    store.close()


def test_dlq_publish_failure_does_not_commit(tmp_path, monkeypatch):
    """A failed dead-letter publish leaves the input for redelivery."""
    bus = MemoryBus()
    publish(bus, value=b"broken")
    store = Handled(tmp_path / "handled.sqlite")
    subscription = bus.consume(["desk.tickets"], "triage")
    record = subscription.poll()

    def fail(*args):
        """Simulate an unavailable dead-letter topic."""
        raise OSError("Broker down")

    monkeypatch.setattr(bus, "publish", fail)
    runner = Runner(bus, store, "triage", "triage", lambda message, connection: None)
    with pytest.raises(OSError):
        runner.process(record, subscription)
    subscription.close()
    assert bus.consume(["desk.tickets"], "triage").poll().value == b"broken"
    store.close()


def test_replay_rejects_missing_source():
    """Replay rejects a dead letter without a valid source topic."""
    bus = MemoryBus()
    bus.publish(DEAD_LETTER_TOPIC, "T-1", b"body", {})
    with pytest.raises(BadMessage, match="dlq-source-topic"):
        replay(bus, list_dead_letters(bus)[0])
