"""Check KafkaBus against a real broker. Opt-in: set AGENT_DESK_KAFKA_BOOTSTRAP."""

import time
import uuid

import pytest

from agent_desk.kafka_bus import create_topics

pytestmark = pytest.mark.kafka


def poll_until(consumer, seconds=30):
    """Poll until a record arrives. The first poll of a new group is slow: it must join the group."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        record = consumer.poll()
        if record is not None:
            return record
    raise AssertionError("no record arrived in time")


def test_round_trip_with_headers(bus, topic):
    """Key, value and headers come back as they were sent."""
    bus.publish(topic, "T-1", b"body", {"traceparent": b"00-abc", "attempt": b"1"})
    consumer = bus.consume([topic], f"g-{uuid.uuid4().hex[:8]}")
    try:
        record = poll_until(consumer)
        assert (record.topic, record.key, record.value) == (topic, "T-1", b"body")
        assert record.headers == {"traceparent": b"00-abc", "attempt": b"1"}
        consumer.commit(record)
    finally:
        consumer.close()


def test_topics_create_is_repeatable(bootstrap):
    """Creating the same topic twice does not fail."""
    name = f"test.{uuid.uuid4().hex[:12]}"
    create_topics(bootstrap, [name])
    create_topics(bootstrap, [name])


def test_failed_handler_is_redelivered(bus, topic):
    """No commit means the next consumer in the same group gets the record again."""
    group = f"g-{uuid.uuid4().hex[:8]}"
    bus.publish(topic, "T-1", b"body", {})
    first = bus.consume([topic], group)
    record = poll_until(first)
    first.close()  # the handler "failed": close without commit
    second = bus.consume([topic], group)
    try:
        again = poll_until(second)
        assert (again.offset, again.value) == (record.offset, b"body")
        second.commit(again)
    finally:
        second.close()
    third = bus.consume([topic], group)
    try:
        # After the commit, nothing is left for this group.
        assert third.poll() is None
    finally:
        third.close()
