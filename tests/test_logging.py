"""Check JSON fields and secret removal on success, retry and poison paths."""

from io import StringIO
import json
import os

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_desk.bus import MemoryBus
from agent_desk.handled import Handled
from agent_desk.runner import Runner
from agent_desk.telemetry import configure_telemetry
from test_resolver import work


def test_json_fields_and_no_secrets(tmp_path, monkeypatch):
    """Even a provider exception or malicious ticket id cannot leak an env key."""
    stream = StringIO()
    configure_telemetry(exporter=InMemorySpanExporter(), stream=stream)
    secret = "fictional-credential-\"with-newline\n"
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_NIM_API_KEY"):
        monkeypatch.setenv(name, secret)
    bus = MemoryBus()
    store = Handled(tmp_path / "handled.sqlite")
    message = work(ticket=secret)
    bus.publish("desk.work", message.ticket_id, message.model_dump_json().encode(), {})
    bus.publish("desk.work", "poison", b"invalid", {})
    calls = []

    def fail(message, connection):
        """Raise an exception that contains a configured credential."""
        calls.append(1)
        raise RuntimeError(os.environ["GEMINI_API_KEY"])

    subscription = bus.consume(["desk.work"], "test")
    try:
        Runner(bus, store, "resolve", "resolve", fail, sleep=lambda delay: None).run(subscription)
    finally:
        subscription.close()
        store.close()
    lines = stream.getvalue().splitlines()
    assert len(calls) == 3
    events = [json.loads(line) for line in lines]
    required = {"ts", "level", "component", "ticket_id", "message_id", "trace_id", "attempt", "event"}
    assert all(set(event) >= required for event in events)
    assert all(int(event["trace_id"], 16) for event in events)
    assert {event["attempt"] for event in events} == {0, 1, 2, 3}
    assert secret not in stream.getvalue() and "fictional-credential" not in stream.getvalue()
    assert {event["event"] for event in events} >= {"handle", "failed", "bad_message"}
