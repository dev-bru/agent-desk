"""Carry trace context across messages and write safe JSON event logs."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
import sys

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


_provider = None
_logger = logging.getLogger("agent_desk.events")
_logger.setLevel(logging.INFO)
_logger.propagate = True
_propagator = TraceContextTextMapPropagator()


def redact(text: str) -> str:
    """Remove configured provider key values before writing text."""
    for name in ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_NIM_API_KEY"):
        value = os.environ.get(name)
        if value:
            text = text.replace(value, "[redacted]")
    return text


def configure_telemetry(*, exporter=None, stream=None):
    """Use a local exporter and JSON logs; no OTLP connection is created."""
    global _provider
    if _provider is not None:
        _provider.shutdown()
    _provider = TracerProvider()
    _provider.add_span_processor(SimpleSpanProcessor(
        exporter if exporter is not None else ConsoleSpanExporter(out=sys.__stderr__)))
    for handler in _logger.handlers[:]:
        _logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(stream if stream is not None else sys.__stderr__)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    return _provider


@contextmanager
def ticket_span(component: str, ticket_id: str, topic: str, headers=None):
    """Start a child span from wire headers, or a root for a new ticket."""
    if _provider is None:
        configure_telemetry()
    carrier = {key: value.decode("ascii", errors="replace") for key, value in (headers or {}).items()
               if key == "traceparent"}
    context = _propagator.extract(carrier) if headers is not None else None
    with _provider.get_tracer("agent_desk").start_as_current_span(
        component, context=context, attributes={"ticket_id": redact(ticket_id), "topic": topic},
        record_exception=False, set_status_on_exception=False,
    ) as span:
        yield span


def message_headers(ticket_id: str, stage: str) -> dict[str, bytes]:
    """Attach the active trace and a stable stage key to an outgoing message."""
    carrier = {}
    _propagator.inject(carrier)
    return {"idempotency-key": f"{ticket_id}:{stage}".encode("utf-8"),
            "attempt": b"1", **{key: value.encode("ascii") for key, value in carrier.items()}}


def log_event(component: str, ticket_id: str, message_id: str, attempt: int, event: str,
              level: str = "INFO") -> None:
    """Log fixed event names and ids without ticket bodies or exception text."""
    if _provider is None:
        configure_telemetry()
    context = trace.get_current_span().get_span_context()
    fields = {
        "ts": datetime.now(timezone.utc).isoformat(), "level": level, "component": component,
        "ticket_id": ticket_id, "message_id": str(message_id), "trace_id": f"{context.trace_id:032x}",
        "attempt": attempt, "event": event, "message": f"{event} attempt={attempt}",
    }
    _logger.log(getattr(logging, level), json.dumps({
        key: redact(value) if isinstance(value, str) else value for key, value in fields.items()
    }, ensure_ascii=False))
