"""Share a topic within one group and copy it to another group."""

import argparse

from agent_desk.approver import read_topic
from agent_desk.bus import MemoryBus


def main():
    """Show group sharing, independent readers, and redelivery."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", required=True, help="Use the offline memory bus")
    parser.parse_args()
    bus = MemoryBus()
    for key in ("T-1", "T-2"):
        bus.publish("desk.tickets", key, key.encode(), {})
    one = bus.consume(["desk.tickets"], "triage")
    two = bus.consume(["desk.tickets"], "triage")
    try:
        left, right = one.poll(), two.poll()
        assert (left.key, right.key) == ("T-1", "T-2")
        two.commit(right)
        one.close()
        repeated = two.poll()
        assert repeated.key == "T-1"
        two.commit(repeated)
        assert two.poll() is None
        print("triage workers: T-1 and T-2; uncommitted T-1 redelivered")
        audit = read_topic(bus, "desk.tickets")
        assert [record.key for record in audit] == ["T-1", "T-2"]
        print("independent audit group: T-1, T-2")
    finally:
        one.close()
        two.close()


if __name__ == "__main__":
    main()
