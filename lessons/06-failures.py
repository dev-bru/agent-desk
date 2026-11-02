"""Retry temporary failures and replay a dead letter after repair."""

import argparse

from agent_desk.bus import MemoryBus
from agent_desk.handled import Handled
from agent_desk.messages import parse_message
from agent_desk.runner import Runner, list_dead_letters, replay


def main():
    """Show bounded retries, duplicate safety, poison isolation, and replay."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", required=True, help="Use the memory bus and a recorded clock")
    parser.parse_args()
    bus = MemoryBus()
    message = parse_message('{"message_id":"00000000-0000-0000-0000-000000000001","ticket_id":"T-1","type":"ticket.created","created_at":"2026-11-02T10:00:00Z","payload":{"customer_id":"C-1","text":"Help","channel":"email"}}')
    value = message.model_dump_json().encode()
    bus.publish("desk.tickets", "poison", b"broken JSON", {})
    bus.publish("desk.tickets", "T-1", value, {})
    bus.publish("desk.tickets", "T-1", value, {})
    store = Handled(":memory:")
    store.connection.execute("CREATE TABLE effects (ticket TEXT)")
    calls, delays = [], []

    def handle(ticket, connection):
        """Fail until the service is repaired, then save one effect."""
        calls.append(ticket.ticket_id)
        connection.execute("INSERT INTO effects VALUES (?)", (ticket.ticket_id,))
        if len(calls) <= 3:
            raise OSError("Temporary service failure")

    consumer = bus.consume(["desk.tickets"], "lesson")
    runner = Runner(bus, store, "lesson", "triage", handle, sleep=delays.append, jitter=lambda low, high: 0)
    try:
        assert runner.run(consumer) == 3
        poison, failed = list_dead_letters(bus)
        assert poison.headers["dlq-attempts"] == b"0"
        assert failed.headers["dlq-attempts"] == b"3"
        assert delays == [1.0, 2.0] and len(calls) == 4
        assert store.connection.execute("SELECT * FROM effects").fetchall() == [("T-1",)]
        print("Dead letters: poison attempts=0; T-1 attempts=3; retry delays=[1.0, 2.0]")
        replay(bus, failed)
        assert runner.run(consumer) == 1
        assert len(calls) == 4
        assert store.connection.execute("SELECT COUNT(*) FROM effects").fetchone() == (1,)
        print("Next delivery succeeded after repair; replay skipped its handled key; 1 saved effect")
        print("Delivery is at-least-once; exactly-once is not claimed")
    finally:
        consumer.close()
        store.close()


if __name__ == "__main__":
    main()
