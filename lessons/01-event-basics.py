"""Send one event through a memory topic and acknowledge it."""

import argparse

from agent_desk.bus import MemoryBus
from agent_desk.messages import parse_message


def main():
    """Read an event, then commit it so this group is done."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", required=True, help="Use the offline memory bus")
    parser.parse_args()
    bus = MemoryBus()
    value = b'{"message_id":"00000000-0000-0000-0000-000000000001","ticket_id":"T-1","type":"ticket.created","created_at":"2026-11-02T10:00:00Z","payload":{"customer_id":"C-1","text":"Where is my mug?","order_id":"O-1","channel":"email"}}'
    bus.publish("desk.tickets", "T-1", value, {})
    consumer = bus.consume(["desk.tickets"], "reader")
    try:
        record = consumer.poll()
        message = parse_message(record.value)
        assert message.ticket_id == record.key == "T-1"
        print(f"Read {message.type} for {message.ticket_id} at offset {record.offset}")
        consumer.commit(record)
        assert consumer.poll() is None
        print("Committed; no pending event")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
