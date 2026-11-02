"""Run the six lessons with external services blocked in each child process."""

import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
LESSONS = [
    "01-event-basics", "02-consumer-groups", "03-agent-as-consumer",
    "04-graph-state", "05-approvals", "06-failures",
]


@pytest.mark.parametrize("name", LESSONS)
def test_lesson_runs_offline(name, tmp_path):
    """Run each script twice with no external services, keys, or shared state."""
    script = ROOT / "lessons" / f"{name}.py"
    document = script.with_suffix(".md").read_text(encoding="utf-8")
    expected = re.search(r"```text\n(.*?)\n```", document, re.DOTALL)
    assert expected, f"{name} needs a literal expected output block"
    environment = os.environ.copy()
    for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_NIM_API_KEY", "AGENT_DESK_KAFKA_BOOTSTRAP"):
        environment.pop(key, None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # The parent's pytest socket guard does not reach a child interpreter.
    bootstrap = (
        "import ipaddress, runpy, socket, sys\n"
        "from agent_desk.model import Model\n"
        "def blocked(*args, **kwargs):\n"
        "    raise AssertionError('Lesson attempted a live model call')\n"
        "Model.chat = blocked\n"
        "connect, connect_ex = socket.socket.connect, socket.socket.connect_ex\n"
        "def check(address):\n"
        "    if not isinstance(address, tuple):\n"
        "        raise AssertionError('Lesson attempted an external connection')\n"
        "    host, port = address[:2]\n"
        "    loopback = host == 'localhost' or ipaddress.ip_address(host).is_loopback\n"
        "    if not loopback or port == 9092:\n"
        "        raise AssertionError('Lesson attempted an external or Kafka connection')\n"
        "def guarded_connect(sock, address):\n"
        "    check(address)\n"
        "    return connect(sock, address)\n"
        "def guarded_connect_ex(sock, address):\n"
        "    check(address)\n"
        "    return connect_ex(sock, address)\n"
        "socket.socket.connect = guarded_connect\n"
        "socket.socket.connect_ex = guarded_connect_ex\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-B", "-c", bootstrap, str(script), "--fake"],
            cwd=tmp_path, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == expected.group(1).strip()


def test_six_lesson_pairs():
    """Keep one document and one script for each required concept."""
    for suffix in (".py", ".md"):
        assert sorted(path.stem for path in (ROOT / "lessons").glob(f"[0-9][0-9]-*{suffix}")) == LESSONS


@pytest.mark.parametrize("name", LESSONS)
def test_lesson_teaches_the_run(name):
    """Require the concept, command, output, source references, and quiz."""
    document = (ROOT / "lessons" / f"{name}.md").read_text(encoding="utf-8")
    for label in ("Concept:", "Expected output", "Files to read", "Quiz:", "MemoryBus", "F-010"):
        assert label in document, f"{name}: missing {label}"
    assert f"lessons/{name}.py --fake" in document
    assert "docs/learn/" in document
    assert re.search(r"src/agent_desk/[\w]+\.py:\d+", document)
