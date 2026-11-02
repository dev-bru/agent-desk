"""Check LiteLLM requests and errors without making a model call."""

from types import SimpleNamespace

import pytest

from agent_desk.model import Model, ModelDown, ModelError, ModelTimeout
from agent_desk.settings import Settings

import litellm


def test_chat_arguments(monkeypatch):
    """Pass the endpoint, model, tools, and timeout without changing input."""
    calls = []
    messages = [{"role": "user", "content": "Hello"}]
    tools = [{"type": "function", "function": {"name": "lookup_order"}}]

    def complete(**kwargs):
        """Record the request and return a tool reply."""
        calls.append(kwargs)
        kwargs["messages"][0]["content"] = "changed by provider"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=None, tool_calls=[SimpleNamespace(id="1", function=SimpleNamespace(
                name="lookup_order", arguments='{"order_id":"O-1"}',
            ))],
        ))])

    monkeypatch.setattr(litellm, "completion", complete)
    model = Model(Settings(model="openai/qwen", api_base="http://127.0.0.1:8080/v1"), timeout=12)
    reply = model.chat(messages, tools)
    assert reply.text == ""
    assert reply.tool_calls[0].name == "lookup_order"
    assert calls[0]["model"] == "openai/qwen"
    assert calls[0]["api_base"] == "http://127.0.0.1:8080/v1"
    assert calls[0]["timeout"] == 12
    assert calls[0]["max_retries"] == 0
    assert calls[0]["tools"] == tools
    assert messages[0]["content"] == "Hello"


@pytest.mark.parametrize("provider,key", [
    ("gemini", "GEMINI_API_KEY"), ("groq", "GROQ_API_KEY"), ("nvidia_nim", "NVIDIA_NIM_API_KEY"),
])
def test_provider_keys(monkeypatch, provider, key):
    """Read only the named environment key and never include it in errors."""
    monkeypatch.delenv(key, raising=False)
    model = Model(Settings(model=f"{provider}/demo"))
    with pytest.raises(ModelError, match=key):
        model.chat([])
    monkeypatch.setenv(key, "fictional-test-value")

    def fail(**kwargs):
        """Echo a fake credential as an untrusted provider error."""
        assert kwargs["api_key"] == "fictional-test-value"
        raise RuntimeError("fictional-test-value")

    monkeypatch.setattr(litellm, "completion", fail)
    with pytest.raises(ModelError) as error:
        model.chat([])
    assert "fictional-test-value" not in str(error.value)


@pytest.mark.parametrize("kind,expected", [
    ("connection", ModelDown), ("timeout", ModelTimeout), ("bad_request", ModelError),
])
def test_error_mapping(monkeypatch, kind, expected):
    """Map real LiteLLM exception types to safe local errors."""
    error_type = {"connection": litellm.APIConnectionError, "timeout": litellm.Timeout,
                  "bad_request": litellm.BadRequestError}[kind]

    def fail(**kwargs):
        """Raise the same exception type as a failing provider."""
        raise error_type(message="private provider detail", model="qwen", llm_provider="openai")

    monkeypatch.setattr(litellm, "completion", fail)
    model = Model(Settings(api_base="http://localhost:8080/v1"))
    with pytest.raises(expected) as error:
        model.chat([])
    assert "private provider detail" not in str(error.value)


def test_paid_or_remote_openai_is_rejected():
    """A local model setting cannot select a paid OpenAI endpoint."""
    with pytest.raises(ModelError, match="loopback"):
        Model(Settings(api_base="https://api.openai.com/v1")).chat([])
