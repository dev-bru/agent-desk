"""Check the package setup and offline test rules."""

from pathlib import Path
import os
import re
import socket
import subprocess
import sys
import tomllib

import pytest


def test_dependencies():
    """Every direct package has an exact lock entry and a recorded version."""
    project = tomllib.loads(Path("pyproject.toml").read_text())
    locked = {p["name"]: p["version"] for p in tomllib.loads(Path("uv.lock").read_text())["package"]}
    record = Path("docs/DEPENDENCIES.md").read_text()
    for dependency in project["project"]["dependencies"] + project["dependency-groups"]["dev"]:
        name, version = dependency.split("==")
        assert locked[name] == version
        assert f"| {name} | {version} |" in record


def test_cli_help():
    """The installed entry point lists the first four commands."""
    executable = Path(sys.executable).with_name("agent-desk.exe")
    result = subprocess.run([str(executable), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    for command in ("simulate", "run", "approve", "eval"):
        assert command in result.stdout


def test_no_secrets_or_user_paths():
    """Source and teaching files contain no key values or user home paths."""
    patterns = [r"sk-" + r"[A-Za-z0-9]{16,}", r"AIza" + r"[A-Za-z0-9_-]{20,}", r"gsk_" + r"[A-Za-z0-9]{16,}", r"nvapi-" + r"[A-Za-z0-9_-]{16,}", r"[A-Za-z]:[/\\]Users[/\\]", r"/home/" + r"[^/\s]+/"]
    paths = [Path("agent-desk.example.toml")]
    for root in ("src", "tests", "lessons"):
        paths.extend(p for p in Path(root).rglob("*") if p.suffix in {".py", ".md", ".toml"})
    for path in paths:
        assert not any(re.search(pattern, path.read_text(encoding="utf-8")) for pattern in patterns), path


@pytest.mark.parametrize("address", [("192.0.2.1", 80), ("127.0.0.1", 9092), ("::1", 9092)])
def test_socket_guard(address):
    """Both socket connect calls reject external and broker addresses."""
    with socket.socket() as sock:
        for method in (sock.connect, sock.connect_ex):
            with pytest.raises(OSError, match="Offline tests block"):
                method(address)


def test_markers():
    """The default command excludes registered network test markers."""
    options = tomllib.loads(Path("pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    assert options["addopts"] == "-m 'not live and not kafka'"
    assert {marker.split(":")[0] for marker in options["markers"]} >= {"live", "kafka"}


def test_marker_selection_in_pytest(tmp_path):
    """Real pytest runs deselect network tests and skip Kafka without an address."""
    project = tomllib.loads(Path("pyproject.toml").read_text())
    options = project["tool"]["pytest"]["ini_options"]
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = " + options["addopts"] + "\nmarkers =\n    "
        + "\n    ".join(options["markers"]) + "\n", encoding="utf-8"
    )
    (tmp_path / "conftest.py").write_text(Path("tests/conftest.py").read_text(), encoding="utf-8")
    (tmp_path / "test_selection.py").write_text(
        '"""Probe network test selection."""\nimport pytest\n'
        'def test_offline():\n    """Run offline."""\n    pass\n'
        '@pytest.mark.kafka\ndef test_kafka():\n    """Run with a broker."""\n    pass\n'
        '@pytest.mark.live\ndef test_live():\n    """Run with a model."""\n    pass\n', encoding="utf-8"
    )
    environment = os.environ.copy()
    environment.pop("AGENT_DESK_KAFKA_BOOTSTRAP", None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    for args, expected in (([], "1 passed, 2 deselected"), (["-m", "kafka"], "1 skipped, 2 deselected"), (["-m", "live"], "1 passed, 2 deselected")):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *args], cwd=tmp_path,
            env=environment, capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert expected in result.stdout


def test_socket_guard_allows_loopback():
    """Local web tools can still connect on a non-broker port."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        for method in ("connect", "connect_ex"):
            with socket.socket() as client:
                client.settimeout(1)
                result = getattr(client, method)(server.getsockname())
                assert result in (None, 0)
                connection, _ = server.accept()
                connection.close()
