"""Replay fixed model replies without a model server or network."""

from copy import deepcopy
import json
from pathlib import Path

from agent_desk.model import Reply, ToolCall


class ScriptExhausted(RuntimeError):
    """Report that the script has no replies left."""


class ScriptedModel:
    """Return a JSON list of text or tool replies in order."""

    def __init__(self, script: list[dict] | str | Path):
        """Read and check a list or a JSON script file."""
        if isinstance(script, (str, Path)):
            script = json.loads(Path(script).read_text(encoding="utf-8"))
        if not isinstance(script, list):
            raise ValueError("script must be a list")
        for index, reply in enumerate(script):
            if not isinstance(reply, dict) or set(reply) not in ({"text"}, {"tool_calls"}):
                raise ValueError(f"reply {index}: use text or tool_calls")
            if "text" in reply:
                if not isinstance(reply["text"], str):
                    raise ValueError(f"reply {index}: text must be a string")
            else:
                calls = reply["tool_calls"]
                if not isinstance(calls, list) or not calls:
                    raise ValueError(f"reply {index}: tool_calls must be a nonempty list")
                for call in calls:
                    if (not isinstance(call, dict) or set(call) != {"name", "arguments"}
                            or not isinstance(call["name"], str) or not isinstance(call["arguments"], str)):
                        raise ValueError(f"reply {index}: invalid tool call")
                    if not isinstance(json.loads(call["arguments"]), dict):
                        raise ValueError(f"reply {index}: tool arguments must be an object")
        self.script = deepcopy(script)
        self.requests = []
        self._index = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        """Save an independent request and return the next scripted reply."""
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        if self._index == len(self.script):
            raise ScriptExhausted("Script has no replies left")
        reply = self.script[self._index]
        self._index += 1
        return Reply(reply.get("text", ""), [
            ToolCall(f"call_{self._index}_{index}", call["name"], call["arguments"])
            for index, call in enumerate(reply.get("tool_calls", []))
        ])
