"""Send chat requests through LiteLLM with keys from the environment only."""

from copy import deepcopy
from dataclasses import dataclass, field
import math
import os
from urllib.parse import urlsplit

from agent_desk.settings import Settings, load_settings

# LiteLLM must not read a dotenv file or download its price table at import.
os.environ["LITELLM_MODE"] = "PRODUCTION"
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"


@dataclass(frozen=True)
class ToolCall:
    """Keep one tool request returned by the model."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Reply:
    """Keep the model text and any tool requests."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ModelError(RuntimeError):
    """Report a bad request or reply without exposing provider details."""


class ModelDown(ModelError):
    """Report that the model cannot be reached."""


class ModelTimeout(ModelError):
    """Report that the model took too long."""


class Model:
    """Use a local model or one of the three configured free providers."""

    def __init__(self, settings: Settings | None = None, *, timeout: float = 30):
        """Keep the endpoint settings and a finite request timeout."""
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self.settings = settings if settings is not None else load_settings()
        self.timeout = timeout

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        """Ask for one reply and map provider failures to desk errors."""
        provider = self.settings.model.split("/", 1)[0]
        key_name = {
            "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "nvidia_nim": "NVIDIA_NIM_API_KEY",
        }.get(provider)
        if key_name:
            key = os.environ.get(key_name)
            if not key:
                raise ModelError(f"Set {key_name} before using this provider")
        elif provider == "openai":
            endpoint = urlsplit(self.settings.api_base or "")
            if (endpoint.scheme not in {"http", "https"}
                    or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
                    or endpoint.username or endpoint.password):
                raise ModelError("The local openai model needs a loopback api_base")
            key = "local"
        else:
            raise ModelError("Use a local openai model, gemini, groq, or nvidia_nim")

        import litellm

        litellm.suppress_debug_info = True
        litellm.telemetry = False
        litellm.redact_user_api_key_info = True
        kwargs = {
            "model": self.settings.model, "api_base": self.settings.api_base,
            "api_key": key, "timeout": self.timeout, "max_retries": 0,
            "messages": deepcopy(messages),
        }
        if tools is not None:
            kwargs["tools"] = tools
        try:
            response = litellm.completion(**kwargs)
        except (litellm.Timeout, TimeoutError):
            raise ModelTimeout("Model request timed out") from None
        except (litellm.APIConnectionError, ConnectionError):
            raise ModelDown("Cannot connect to the model") from None
        except Exception:
            # Provider exceptions may contain request headers, so do not copy them.
            raise ModelError("Model request failed") from None
        if not response.choices:
            raise ModelError("Model returned no choices")
        message = response.choices[0].message
        return Reply(message.content or "", [
            ToolCall(call.id, call.function.name, call.function.arguments)
            for call in (message.tool_calls or [])
        ])
