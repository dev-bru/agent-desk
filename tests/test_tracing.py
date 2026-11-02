"""Follow one trace through work, a human decision and a resumed result."""

from io import StringIO

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent_desk.approver import decide, read_topic
from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.handled import Handled
from agent_desk.messages import TicketCreatedEnvelope
from agent_desk.resolver import Resolver
from agent_desk.telemetry import configure_telemetry, log_event, message_headers, ticket_span
from agent_desk.triage import Triage
from test_approval import drain
from test_resolver import shop, work


def test_trace_across_hops(shop, tmp_path, monkeypatch):
    """All producer and consumer spans inherit a single W3C trace id."""
    exporter = InMemorySpanExporter()
    provider = configure_telemetry(exporter=exporter, stream=StringIO())
    settings, tools = shop
    bus = MemoryBus()
    store = Handled(tmp_path / "handled.sqlite")
    triaged = work("refund", "O-2", "C-2").model_dump(mode="json")
    triaged["type"] = "ticket.created"
    del triaged["payload"]["category"], triaged["payload"]["priority"]
    message = TicketCreatedEnvelope.model_validate(triaged)
    with ticket_span("simulate", "T-1", "desk.tickets"):
        bus.publish("desk.tickets", "T-1", message.model_dump_json().encode(), message_headers("T-1", "triage"))
        log_event("simulate", "T-1", str(message.message_id), 1, "published")
    resolver = Resolver(bus, ScriptedModel([
        {"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":75}'},
    ]), tools, settings)
    try:
        triage = Triage(bus, ScriptedModel([{"text": '{"category":"refund","priority":"normal"}'}]))
        drain(bus, "desk.tickets", triage.runner(store), "triage")
        drain(bus, "desk.work", resolver.runner(store), "resolver")
        resolver.close()
        resolver = Resolver(bus, ScriptedModel([]), tools, settings)
        decide(bus, "T-1", True, "Sam")
        drain(bus, "desk.approvals.decisions", resolver.decision_runner(store), "decisions")
        spans = exporter.get_finished_spans()
        assert {span.name for span in spans} == {"simulate", "triage", "resolve", "approve"}
        assert len(spans) == 5
        assert len({span.context.trace_id for span in spans}) == 1
        assert all(span.attributes["ticket_id"] == "T-1" and span.attributes["topic"].startswith("desk.")
                   for span in spans)
        root = next(span for span in spans if span.name == "simulate")
        assert root.parent is None
        assert all(span.parent is not None for span in spans if span.name != "simulate")
        result = read_topic(bus, "desk.results")[0]
        assert result.headers["traceparent"].decode().split("-")[1] == f"{root.context.trace_id:032x}"
        assert provider.force_flush()
    finally:
        resolver.close()
        store.close()


def test_default_exporter_is_local(monkeypatch):
    """Even OTEL environment settings cannot enable a network exporter by default."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://external.invalid:4318")
    provider = configure_telemetry(stream=StringIO())
    processors = provider._active_span_processor._span_processors
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter
    assert len(processors) == 1
    assert isinstance(processors[0].span_exporter, ConsoleSpanExporter)
