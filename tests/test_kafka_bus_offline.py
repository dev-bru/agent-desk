"""Check KafkaBus rules with fake clients, so no broker is needed."""

import pytest
from confluent_kafka import KafkaError, KafkaException

from agent_desk.kafka_bus import BrokerUnavailable, KafkaBus, check_broker, create_topics


class FakeMessage:
    """Look like a confluent_kafka message."""

    def __init__(self, offset, partition=2, error=None):
        self._offset, self._partition, self._error = offset, partition, error

    def error(self): return self._error
    def topic(self): return "desk.tickets"
    def partition(self): return self._partition
    def offset(self): return self._offset
    def key(self): return b"T-1"
    def value(self): return b"body"
    def headers(self): return [("traceparent", b"abc")]


class FakeConsumer:
    """Replay messages and write every call to a shared log."""

    def __init__(self, log, messages=()):
        self.log, self.messages = log, list(messages)

    def subscribe(self, topics): self.log.append(("subscribe", topics))
    def poll(self, timeout): return self.messages.pop(0) if self.messages else None

    def commit(self, offsets, asynchronous):
        self.log.append(("commit", offsets[0].partition, offsets[0].offset, asynchronous))

    def close(self): self.log.append(("close",))


class FakeProducer:
    """Confirm the delivery at once, or fail it."""

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def produce(self, topic, key, value, headers, on_delivery):
        self.sent.append((topic, key, value, headers))
        on_delivery(KafkaError(KafkaError._MSG_TIMED_OUT) if self.fail else None, None)

    def flush(self, timeout): return 0


def make_bus(log, messages=(), producer=None):
    """Build a KafkaBus on fakes."""
    return KafkaBus("127.0.0.1:9092", producer_factory=lambda config: producer or FakeProducer(),
                    consumer_factory=lambda config: FakeConsumer(log, messages))


def test_commit_only_after_handler_returns():
    """The log shows handled first, commit second. The commit is synchronous and points to offset + 1."""
    log = []
    consumer = make_bus(log, [FakeMessage(7)]).consume(["desk.tickets"], "triage")
    record = consumer.poll()
    assert (record.key, record.value, record.headers, record.offset) == ("T-1", b"body", {"traceparent": b"abc"}, 7)
    assert not any(entry[0] == "commit" for entry in log)
    log.append(("handled",))
    consumer.commit(record)
    assert log[-2:] == [("handled",), ("commit", 2, 8, False)]
    assert consumer.poll() is None


def test_failed_handler_does_not_commit():
    """Without a commit, poll keeps returning the same record, and close commits nothing."""
    log = []
    consumer = make_bus(log, [FakeMessage(0), FakeMessage(1)]).consume(["desk.tickets"], "triage")
    record = consumer.poll()
    assert consumer.poll() is record
    consumer.close()
    assert [entry[0] for entry in log] == ["subscribe", "close"]


def test_commit_needs_the_pending_record():
    """A record this consumer does not hold cannot be committed."""
    consumer = make_bus([], [FakeMessage(0)]).consume(["desk.tickets"], "triage")
    record = consumer.poll()
    consumer.commit(record)
    with pytest.raises(ValueError):
        consumer.commit(record)


def test_broker_error_message_is_raised():
    """A message with an error is not handed out as a record."""
    consumer = make_bus([], [FakeMessage(0, error=KafkaError(KafkaError._TRANSPORT))]).consume(["desk.tickets"], "g")
    with pytest.raises(KafkaException):
        consumer.poll()


def test_publish_sends_bytes_and_raises_on_failure():
    """Key and headers go out as bytes. A failed delivery raises."""
    producer = FakeProducer()
    make_bus([], producer=producer).publish("desk.tickets", "T-1", b"body", {"attempt": b"1"})
    assert producer.sent == [("desk.tickets", b"T-1", b"body", [("attempt", b"1")])]
    with pytest.raises(KafkaException):
        make_bus([], producer=FakeProducer(fail=True)).publish("desk.tickets", "T-1", b"x", {})


def test_check_broker_gives_one_clear_message():
    """No answer from the broker becomes one BrokerUnavailable with the start command."""
    class Silent:
        def __init__(self, config): pass
        def list_topics(self, timeout): raise KafkaException(KafkaError(KafkaError._TRANSPORT))

    with pytest.raises(BrokerUnavailable, match=r"No Kafka broker answered at 127.0.0.1:9 .*kafka-local.ps1 start"):
        check_broker("127.0.0.1:9", 1, admin_factory=Silent)


def test_create_topics_skips_existing():
    """TOPIC_ALREADY_EXISTS is fine; another error is raised."""
    class Done:
        def __init__(self, code): self.code = code

        def result(self):
            if self.code is not None:
                raise KafkaException(KafkaError(self.code))

    class Admin:
        code = KafkaError.TOPIC_ALREADY_EXISTS

        def __init__(self, config): pass
        def create_topics(self, topics): return {topic.topic: Done(self.code) for topic in topics}

    create_topics("x:1", ["a", "b"], admin_factory=Admin)
    Admin.code = KafkaError.INVALID_CONFIG
    with pytest.raises(KafkaException):
        create_topics("x:1", ["a"], admin_factory=Admin)
