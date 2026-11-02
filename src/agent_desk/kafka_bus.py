"""Run the Bus interface on a real Kafka broker, and create the desk topics.

Delivery is at-least-once. The rule that makes it so: a consumer commits an offset only AFTER the
handler has finished. If the program dies before the commit, Kafka hands the same record out again.
"""

from collections.abc import Callable
from typing import Any

from confluent_kafka import Consumer as KafkaConsumer
from confluent_kafka import KafkaError, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from agent_desk.bus import Record

DESK_TOPICS = (
    "desk.tickets", "desk.work", "desk.approvals.requests",
    "desk.approvals.decisions", "desk.results", "desk.dead-letter",
)


class BrokerUnavailable(RuntimeError):
    """Say in one clear sentence that no broker answered."""


def check_broker(bootstrap: str, timeout_s: float = 5.0, admin_factory: Callable[[dict], Any] = AdminClient) -> None:
    """Ask the broker for its metadata. Fail fast with one clear message if it does not answer."""
    try:
        admin_factory({"bootstrap.servers": bootstrap}).list_topics(timeout=timeout_s)
    except KafkaException as exc:
        raise BrokerUnavailable(
            f"No Kafka broker answered at {bootstrap} within {timeout_s:g} s. "
            "Start it with: powershell -File scripts/kafka-local.ps1 start"
        ) from exc


def create_topics(bootstrap: str, names=DESK_TOPICS, partitions: int = 1,
                  admin_factory: Callable[[dict], Any] = AdminClient) -> None:
    """Create topics. Running it again is safe: a topic that exists is skipped."""
    admin = admin_factory({"bootstrap.servers": bootstrap})
    futures = admin.create_topics([NewTopic(name, num_partitions=partitions, replication_factor=1) for name in names])
    for future in futures.values():
        try:
            future.result()
        except KafkaException as exc:
            if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise


class KafkaBus:
    """Publish to and read from Kafka with the same methods as MemoryBus."""

    def __init__(self, bootstrap: str, producer_factory: Callable[[dict], Any] = Producer,
                 consumer_factory: Callable[[dict], Any] = KafkaConsumer, poll_timeout_s: float = 1.0):
        self._bootstrap = bootstrap
        self._consumer_factory = consumer_factory
        self._poll_timeout_s = poll_timeout_s
        # acks=all: the broker confirms only when the record is safely stored.
        self._producer = producer_factory({"bootstrap.servers": bootstrap, "acks": "all"})

    def publish(self, topic: str, key: str, value: bytes, headers: dict[str, bytes]) -> None:
        """Send one record and wait until the broker confirms it."""
        errors = []

        def on_delivery(error, _message):
            """Remember a failed delivery so publish can raise it."""
            if error is not None:
                errors.append(error)

        self._producer.produce(topic, key=key.encode("utf-8"), value=value,
                               headers=list(headers.items()), on_delivery=on_delivery)
        if self._producer.flush(10.0) or errors:
            raise KafkaException(errors[0] if errors else KafkaError(KafkaError._MSG_TIMED_OUT))

    def consume(self, topics: list[str], group: str) -> "KafkaConsumerHandle":
        """Join a consumer group. Workers with the same group name share the topic."""
        client = self._consumer_factory({
            "bootstrap.servers": self._bootstrap,
            "group.id": group,
            # Never let the client commit by itself. Only commit() below moves the bookmark.
            "enable.auto.commit": False,
            # A new group starts at the first record, so no early record is missed.
            "auto.offset.reset": "earliest",
        })
        client.subscribe(list(topics))
        return KafkaConsumerHandle(client, self._poll_timeout_s)


class KafkaConsumerHandle:
    """Hold one delivery until commit or close, like MemoryConsumer."""

    def __init__(self, client: Any, poll_timeout_s: float):
        self._client = client
        self._poll_timeout_s = poll_timeout_s
        self._pending: Record | None = None
        self._partition = 0

    def poll(self) -> Record | None:
        """Return the pending record, else wait a short time for a new one.

        Redelivery works like this: while a record is pending, poll returns it again and never reads
        ahead. If the consumer closes without commit, the group bookmark did not move. The next
        consumer in the group starts at that record.
        """
        if self._pending is not None:
            return self._pending
        message = self._client.poll(self._poll_timeout_s)
        if message is None:
            return None
        if message.error():
            raise KafkaException(message.error())
        headers = {name: bytes(value or b"") for name, value in (message.headers() or [])}
        key = (message.key() or b"").decode("utf-8")
        self._partition = message.partition()
        self._pending = Record(message.topic(), key, message.value(), headers, message.offset())
        return self._pending

    def commit(self, record: Record) -> None:
        """Move the group bookmark past this record. The caller does this only after the handler returned."""
        if record is not self._pending or record is None:
            raise ValueError("Commit requires this consumer's pending record")
        # The committed offset is the NEXT record to read, so add one.
        offsets = [TopicPartition(record.topic, self._partition, record.offset + 1)]
        self._client.commit(offsets=offsets, asynchronous=False)
        self._pending = None

    def close(self) -> None:
        """Leave the group without committing. Uncommitted work is delivered again."""
        self._pending = None
        self._client.close()
