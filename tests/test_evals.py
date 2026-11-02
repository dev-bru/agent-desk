"""Check exact triage scores and saved model metadata without a live call."""

import json

import pytest

from agent_desk.evals import copying_model, evaluate_triage
from agent_desk.simulator import load_tickets


@pytest.mark.parametrize("wrong", [False, True])
def test_accuracy_confusion_and_report(tmp_path, wrong):
    """One wrong category changes the score and the corresponding confusion cell."""
    tickets = load_tickets()
    model = copying_model(tickets)
    expected = tickets[0]
    if wrong:
        model.script[0] = {"text": json.dumps({"category": "other", "priority": expected.priority})}
    result = evaluate_triage(model, tickets, model_name="scripted-test", output_dir=tmp_path)
    assert result["category_accuracy"] == (len(tickets) - int(wrong)) / len(tickets)
    assert result["priority_accuracy"] == 1.0
    assert result["accuracy"] == result["category_accuracy"]
    assert result["confusion"]["category"][expected.category].get("other", 0) == int(wrong)
    reports = list(tmp_path.glob("eval-*.json"))
    assert len(reports) == 1
    saved = json.loads(reports[0].read_text(encoding="utf-8"))
    assert saved == result and saved["model"] == "scripted-test" and saved["set_size"] == len(tickets)
    assert len(model.requests) == len(tickets)
    assert all("category" not in json.loads(request["messages"][1]["content"]) for request in model.requests)


def test_empty_eval_writes_nothing(tmp_path):
    """An empty set cannot produce a misleading accuracy report."""
    with pytest.raises(ValueError, match="nonempty"):
        evaluate_triage(copying_model([]), [], model_name="scripted", output_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []
