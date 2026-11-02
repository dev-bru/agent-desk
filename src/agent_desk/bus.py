"""Keep ordered topic logs and explicit acknowledgements without a broker."""

from dataclasses import dataclass
from threading import RLock
from typing import Protocol


@dataclass(frozen=True)
class Record:
    """Keep wire data and its position in a topic."""

    topic: str
    key: str
    value: bytes
    headers: dict[str, bytes]
    offset: int


class Consumer(Protocol):
    """Read one record at a time and commit it after handling."""

    def poll(self) -> Record | None:
        """Return a pending record, or None when none is available."""
        ...

    def commit(self, record: Record) -> None:
        """Mark the pending record as handled."""
        ...

    def close(self) -> None:
        """Release pending work so another consumer can read it."""
        ...


class Bus(Protocol):
    """Publish wire data and join a consumer group."""

    def publish(self, topic: str, key: str, value: bytes, headers: dict[str, bytes]) -> None:
        """Append a record to a topic."""
        ...

    def consume(self, topics: list[str], group: str) -> Consumer:
        """Join a group that reads the named topics."""
        ...


class MemoryBus:
    """Model at-least-once delivery for tests in one process."""

    def __init__(self):
        self._logs: dict[str, list[Record]] = {}
        self._committed: dict[tuple[str, str], set[int]] = {}
        self._claims: dict[tuple[str, str, int], MemoryConsumer] = {}
        self._lock = RLock()

    def publish(self, topic: str, key: str, value: bytes, headers: dict[str, bytes]) -> None:
        """Append an independent copy of the wire data."""
        with self._lock:
            log = self._logs.setdefault(topic, [])
            log.append(Record(topic, key, value, dict(headers), len(log)))

    def consume(self, topics: list[str], group: str) -> "MemoryConsumer":
        """Create a consumer with its own pending delivery."""
        return MemoryConsumer(self, topics, group)


class MemoryConsumer:
    """Hold one delivery until commit or close releases it."""

    def __init__(self, bus: MemoryBus, topics: list[str], group: str):
        self._bus = bus
        self._topics = list(topics)
        self._group = group
        self._pending: Record | None = None
        self._closed = False

    def poll(self) -> Record | None:
        """Read unclaimed work while keeping each key in order."""
        with self._bus._lock:
            if self._closed:
                raise RuntimeError("Consumer is closed")
            if self._pending is not None:
                return self._pending
            for topic in self._topics:
                committed = self._bus._committed.setdefault((self._group, topic), set())
                blocked_keys = set()
                for record in self._bus._logs.get(topic, []):
                    if record.offset in committed:
                        continue
                    claim = (self._group, topic, record.offset)
                    if claim in self._bus._claims:
                        blocked_keys.add(record.key)
                        continue
                    if record.key in blocked_keys:
                        continue
                    self._bus._claims[claim] = self
                    self._pending = Record(topic, record.key, record.value, dict(record.headers), record.offset)
                    return self._pending
            return None

    def commit(self, record: Record) -> None:
        """Acknowledge only the delivery owned by this consumer."""
        with self._bus._lock:
            if record is not self._pending or record is None:
                raise ValueError("Commit requires this consumer's pending record")
            self._bus._committed[(self._group, record.topic)].add(record.offset)
            del self._bus._claims[(self._group, record.topic, record.offset)]
            self._pending = None

    def close(self) -> None:
        """Leave uncommitted work available for redelivery."""
        with self._bus._lock:
            if self._pending is not None:
                record = self._pending
                del self._bus._claims[(self._group, record.topic, record.offset)]
                self._pending = None
            self._closed = True
