"""Check ordering, group sharing, and redelivery in memory."""

import pytest

from agent_desk.bus import MemoryBus


def test_same_key_order():
    """A second consumer cannot pass pending work with the same key."""
    bus = MemoryBus()
    for value in (b"first", b"second", b"third"):
        bus.publish("tickets", "T-1", value, {})
    one, two = (bus.consume(["tickets"], "triage") for _ in range(2))
    for consumer, expected in ((one, b"first"), (two, b"second"), (one, b"third")):
        record = consumer.poll()
        assert record.value == expected
        other = two if consumer is one else one
        assert other.poll() is None
        consumer.commit(record)
    assert one.poll() is None


def test_groups_share_without_overlap():
    """Workers share a group while a second group gets the whole log."""
    bus = MemoryBus()
    for index in range(4):
        bus.publish("tickets", str(index), str(index).encode(), {})
    one, two = (bus.consume(["tickets"], "triage") for _ in range(2))
    received = []
    for _ in range(2):
        left, right = one.poll(), two.poll()
        assert left.offset != right.offset
        received.extend([left.value, right.value])
        two.commit(right)
        one.commit(left)
    assert received == [b"0", b"1", b"2", b"3"]
    other = bus.consume(["tickets"], "audit")
    copied = []
    while (record := other.poll()) is not None:
        copied.append(record.value)
        other.commit(record)
    assert copied == received


def test_redelivery_and_headers():
    """Close releases pending work and commit prevents later redelivery."""
    bus = MemoryBus()
    headers = {"traceparent": b"demo"}
    bus.publish("tickets", "T-1", b"body", headers)
    headers["traceparent"] = b"changed"
    one = bus.consume(["tickets"], "triage")
    record = one.poll()
    assert one.poll() is record
    assert record.headers == {"traceparent": b"demo"}
    record.headers["traceparent"] = b"changed"
    one.close()
    two = bus.consume(["tickets"], "triage")
    redelivered = two.poll()
    assert redelivered.headers == {"traceparent": b"demo"}
    with pytest.raises(ValueError):
        two.commit(record)
    two.commit(redelivered)
    two.close()
    assert bus.consume(["tickets"], "triage").poll() is None
