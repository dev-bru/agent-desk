"""Measure triage against labels and save a local JSON report."""

from pathlib import Path
import json
from time import time_ns

from agent_desk.approver import read_topic
from agent_desk.bus import MemoryBus
from agent_desk.fakes import ScriptedModel
from agent_desk.messages import parse_message
from agent_desk.simulator import LabeledTicket, ticket_message
from agent_desk.telemetry import ticket_span
from agent_desk.triage import Triage


def copying_model(tickets: list[LabeledTicket]) -> ScriptedModel:
    """Copy known labels to check the eval plumbing without a live model."""
    return ScriptedModel([{"text": json.dumps({"category": item.category, "priority": item.priority})}
                          for item in tickets])


def evaluate_triage(model, tickets: list[LabeledTicket], *, model_name: str,
                    output_dir: str | Path = "runs") -> dict:
    """Run the real triage handler and count correct labels and confusion cells."""
    if not tickets or len({item.ticket_id for item in tickets}) != len(tickets):
        raise ValueError("Eval needs a nonempty set with unique ticket ids")
    bus = MemoryBus()
    triage = Triage(bus, model)
    for ticket in tickets:
        with ticket_span("triage", ticket.ticket_id, "desk.tickets"):
            triage.handle(ticket_message(ticket), None)
    predictions = [parse_message(record.value).payload for record in read_topic(bus, "desk.work")]
    confusion = {"category": {}, "priority": {}}
    correct = {"category": 0, "priority": 0}
    joint = 0
    for expected, predicted in zip(tickets, predictions, strict=True):
        joint += expected.category == predicted.category and expected.priority == predicted.priority
        for field in correct:
            truth, guess = getattr(expected, field), getattr(predicted, field)
            correct[field] += truth == guess
            row = confusion[field].setdefault(truth, {})
            row[guess] = row.get(guess, 0) + 1
    result = {"model": model_name, "set_size": len(tickets), "accuracy": joint / len(tickets),
              "category_accuracy": correct["category"] / len(tickets),
              "priority_accuracy": correct["priority"] / len(tickets), "confusion": confusion}
    path = Path(output_dir) / f"eval-{time_ns()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return result
