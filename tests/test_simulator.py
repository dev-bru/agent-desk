"""Check labeled data, seeded order, malformed messages and exact repeats."""

from collections import Counter
from io import StringIO

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from agent_desk.approver import read_topic
from agent_desk.bus import MemoryBus
from agent_desk.messages import BadMessage, parse_message
from agent_desk.simulator import load_tickets, simulate
from agent_desk.telemetry import configure_telemetry


def test_labeled_set_and_seed():
    """Forty complete labeled tickets produce a repeatable shuffled order."""
    exporter = InMemorySpanExporter()
    configure_telemetry(exporter=exporter, stream=StringIO())
    tickets = load_tickets()
    assert len(tickets) >= 40
    assert {item.category for item in tickets} == {"refund", "order_status", "shipping", "product", "other"}
    assert all(item.customer_id and item.text and item.ticket_id for item in tickets)
    assert all(item.order_id for item in tickets if item.category in {"refund", "order_status", "shipping"})
    orders = []
    for seed in [42, 42, 7]:
        bus = MemoryBus()
        assert simulate(bus, seed=seed) == 40
        records = read_topic(bus, "desk.tickets")
        orders.append([parse_message(record.value).ticket_id for record in records])
        assert all("traceparent" in record.headers for record in records)
        assert all("category" not in parse_message(record.value).payload.model_dump() for record in records)
    assert orders[0] == orders[1] and orders[0] != orders[2]
    assert len(exporter.get_finished_spans()) == 120


def test_poison_and_duplicates():
    """Poison adds invalid messages and duplicates keep the original message ids."""
    bus = MemoryBus()
    assert simulate(bus, count=5, poison=2, duplicate=2) == 9
    records = read_topic(bus, "desk.tickets")
    assert records[0].value == records[5].value and records[1].value == records[6].value
    messages = [parse_message(record.value) for record in records[:7]]
    assert sorted(Counter(item.message_id for item in messages).values()) == [1, 1, 1, 2, 2]
    for record in records[7:]:
        with pytest.raises(BadMessage):
            parse_message(record.value)


@pytest.mark.parametrize("options", [{"count": -1}, {"count": 41}, {"poison": -1},
                                     {"count": 0, "duplicate": 1}, {"duplicate": -1}])
def test_bad_counts_do_not_publish(options):
    """Reject bad options before writing any tickets."""
    bus = MemoryBus()
    with pytest.raises(ValueError):
        simulate(bus, **options)
    assert read_topic(bus, "desk.tickets") == []
