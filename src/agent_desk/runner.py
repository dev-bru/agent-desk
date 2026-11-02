"""Handle deliveries with durable keys, bounded retries, and dead letters."""

from collections.abc import Callable
import math
import random
import sqlite3
import time
from uuid import uuid4

from agent_desk.bus import Bus, Consumer, Record
from agent_desk.handled import Handled
from agent_desk.messages import BadMessage, Message, parse_message
from agent_desk.telemetry import log_event, redact, ticket_span


DEAD_LETTER_TOPIC = "desk.dead-letter"


class Runner:
    """Commit input only after successful work or a dead-letter publish."""

    def __init__(
        self, bus: Bus, handled: Handled, consumer: str, stage: str,
        handler: Callable[[Message, sqlite3.Connection], None], *,
        max_attempts: int = 3, backoff_base_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ):
        if max_attempts < 1 or not math.isfinite(backoff_base_s) or backoff_base_s < 0:
            raise ValueError("max_attempts must be positive and backoff_base_s finite and nonnegative")
        self.bus = bus
        self.handled = handled
        self.consumer = consumer
        self.stage = stage
        self.handler = handler
        self.max_attempts = max_attempts
        self.backoff_base_s = backoff_base_s
        self.sleep = sleep
        self.jitter = jitter

    def process(self, record: Record, subscription: Consumer) -> None:
        """Retry one delivery, then acknowledge success or its dead letter."""
        component = {"resolver": "resolve", "resolver-decisions": "resolve"}.get(self.consumer, self.consumer)
        with ticket_span(component, record.key, record.topic, record.headers):
            self._process(record, subscription, component)

    def _process(self, record, subscription, component):
        try:
            message = parse_message(record.value)
            key = f"{message.ticket_id}:{self.stage}"
            if record.headers.get("idempotency-key", key.encode()) != key.encode():
                raise BadMessage("Invalid message field: idempotency-key")
        except BadMessage as exc:
            log_event(component, record.key, "", 0, "bad_message", "WARNING")
            self._dead_letter(record, str(exc), 0)
            subscription.commit(record)
            return

        for attempt in range(1, self.max_attempts + 1):
            record.headers["attempt"] = str(attempt).encode()
            log_event(component, message.ticket_id, str(message.message_id), attempt, "handle")
            try:
                self.handled.run(self.consumer, key, lambda connection: self.handler(message, connection))
            except Exception as exc:
                log_event(component, message.ticket_id, str(message.message_id), attempt, "failed", "WARNING")
                if isinstance(exc, BadMessage) or attempt == self.max_attempts:
                    self._dead_letter(record, str(exc), attempt)
                    break
                # Jitter adds from zero to ten percent of the base delay.
                delay = self.backoff_base_s * 2 ** (attempt - 1)
                self.sleep(delay + self.jitter(0, self.backoff_base_s * 0.1))
            else:
                log_event(component, message.ticket_id, str(message.message_id), attempt, "handled")
                break
        subscription.commit(record)

    def run(self, subscription: Consumer) -> int:
        """Handle available records until the subscription has no work."""
        count = 0
        while (record := subscription.poll()) is not None:
            self.process(record, subscription)
            count += 1
        return count

    def _dead_letter(self, record: Record, reason: str, attempts: int) -> None:
        headers = dict(record.headers)
        headers.update({
            "dlq-reason": redact(reason).encode("utf-8"),
            "dlq-source-topic": record.topic.encode("utf-8"),
            "dlq-attempts": str(attempts).encode(),
        })
        self.bus.publish(DEAD_LETTER_TOPIC, record.key, record.value, headers)


def list_dead_letters(bus: Bus) -> list[Record]:
    """Read a fresh view of all available dead letters."""
    subscription = bus.consume([DEAD_LETTER_TOPIC], f"dlq-view-{uuid4()}")
    records = []
    try:
        while (record := subscription.poll()) is not None:
            records.append(record)
            subscription.commit(record)
    finally:
        subscription.close()
    return records


def replay(bus: Bus, record: Record) -> None:
    """Republish a dead letter to its source with a fresh retry count."""
    try:
        topic = record.headers["dlq-source-topic"].decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        raise BadMessage("Invalid message field: dlq-source-topic") from exc
    if not topic or topic == DEAD_LETTER_TOPIC:
        raise BadMessage("Invalid message field: dlq-source-topic")
    headers = {key: value for key, value in record.headers.items() if not key.startswith("dlq-") and key != "attempt"}
    bus.publish(topic, record.key, record.value, headers)
