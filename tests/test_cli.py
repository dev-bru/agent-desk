"""Run the local desk and eval commands with only scripted models."""

from io import StringIO
import json

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from agent_desk.approver import read_topic
from agent_desk.bus import MemoryBus
from agent_desk.cli import main
from agent_desk.messages import parse_message
from agent_desk.simulator import load_tickets
from agent_desk.telemetry import configure_telemetry


def test_simulate_run_results(tmp_path, monkeypatch, capsys):
    """The CLI wires the whole offline pipeline and absorbs duplicates and poison."""
    exporter = InMemorySpanExporter()
    configure_telemetry(exporter=exporter, stream=StringIO())
    monkeypatch.setenv("AGENT_DESK_DB_PATH", str(tmp_path / "shop.sqlite"))
    monkeypatch.setenv("AGENT_DESK_CHECKPOINT_PATH", str(tmp_path / "checkpoints.sqlite"))
    bus = MemoryBus()
    assert main(["simulate", "--seed", "4", "--poison", "2", "--duplicate", "2"], bus=bus) == 0
    assert main(["run", "--fake", "--handled-path", str(tmp_path / "handled.sqlite")], bus=bus) == 0
    assert main(["results"], bus=bus) == 0
    output = capsys.readouterr().out
    assert "Published 44" in output and "TICKET | STATUS | REFUND | REPLY" in output
    assert "Handled triage=44, resolver=40, decisions=0" in output
    results = [parse_message(record.value) for record in read_topic(bus, "desk.results")]
    assert len(results) == 40
    assert {message.payload.status for message in results} == {"resolved", "refunded"}
    assert len(read_topic(bus, "desk.dead-letter")) == 2
    spans = exporter.get_finished_spans()
    assert {span.name for span in spans} == {"simulate", "triage", "resolve"}
    for message in results:
        ticket_spans = [span for span in spans if span.attributes["ticket_id"] == message.ticket_id]
        assert len({span.context.trace_id for span in ticket_spans}) == 1
        assert {span.name for span in ticket_spans} == {"simulate", "triage", "resolve"}
    assert main(["run", "--fake", "--handled-path", str(tmp_path / "handled.sqlite")], bus=bus) == 0
    assert len(read_topic(bus, "desk.results")) == 40


def test_standalone_fake_demo(tmp_path, monkeypatch, capsys):
    """A fresh process can demonstrate both agents without an injected bus."""
    monkeypatch.setenv("AGENT_DESK_DB_PATH", str(tmp_path / "shop.sqlite"))
    monkeypatch.setenv("AGENT_DESK_CHECKPOINT_PATH", str(tmp_path / "checkpoints.sqlite"))
    assert main(["run", "--fake", "--count", "2", "--handled-path", str(tmp_path / "handled.sqlite")]) == 0
    assert "triage=2, resolver=2" in capsys.readouterr().out


def test_eval_cli_fake_and_custom_script(tmp_path, capsys):
    """Fake eval prints perfect scores, and a supplied script changes one category."""
    assert main(["eval", "triage", "--fake", "--output-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Category accuracy: 1.0000" in output and "Priority accuracy: 1.0000" in output
    tickets = load_tickets()
    script = [{"text": json.dumps({"category": item.category, "priority": item.priority})} for item in tickets]
    script[0] = {"text": '{"category":"other","priority":"normal"}'}
    path = tmp_path / "script.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    assert main(["eval", "triage", "--fake", "--script", str(path), "--output-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Category accuracy: 0.9750" in output and "refund | other | 1" in output
    assert len(list(tmp_path.glob("eval-*.json"))) == 2


def test_eval_script_requires_fake(tmp_path):
    """A scripted eval must explicitly select offline mode."""
    with pytest.raises(SystemExit):
        main(["eval", "triage", "--script", str(tmp_path / "script.json")])
