"""Check ordered fake replies and independent request copies."""

import json

import pytest

from agent_desk.fakes import ScriptedModel, ScriptExhausted


def test_script_order_requests_and_exhaustion(tmp_path):
    """Load a JSON script and record the same chat arguments as the real model."""
    path = tmp_path / "script.json"
    path.write_text(json.dumps([
        {"text": "hello"},
        {"tool_calls": [{"name": "lookup_order", "arguments": '{"order_id":"O-1"}'}]},
    ]), encoding="utf-8")
    model = ScriptedModel(path)
    messages = [{"role": "user", "content": "Help"}]
    assert model.chat(messages).text == "hello"
    messages[0]["content"] = "changed"
    tools = [{"name": "lookup_order"}]
    assert model.chat(messages, tools).tool_calls[0].name == "lookup_order"
    tools.clear()
    assert model.requests[0]["messages"][0]["content"] == "Help"
    assert model.requests[1]["tools"] == [{"name": "lookup_order"}]
    with pytest.raises(ScriptExhausted, match="no replies"):
        model.chat([])


@pytest.mark.parametrize("script", [{}, ["text"], [{"text": 1}], [{"tool_calls": []}],
                                       [{"tool_calls": [{"name": "x", "arguments": "[]"}]}]])
def test_bad_script(script):
    """Reject invalid scripts before running an agent."""
    with pytest.raises(ValueError):
        ScriptedModel(script)
