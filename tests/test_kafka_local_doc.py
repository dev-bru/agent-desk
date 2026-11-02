"""Check the broker config template, the start script and the README claims. Offline."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_broker_template_is_kraft_loopback_high_retention():
    """KRaft roles, no ZooKeeper, loopback listeners, and retention of years."""
    text = (ROOT / "config" / "kafka" / "server.properties").read_text(encoding="utf-8")
    settings = dict(line.split("=", 1) for line in text.splitlines() if line and not line.startswith("#"))
    assert settings["process.roles"] == "broker,controller"
    assert "zookeeper" not in text.lower()
    for key in ("listeners", "advertised.listeners", "controller.quorum.bootstrap.servers"):
        assert "0.0.0.0" not in settings[key]
        assert set(re.findall(r"\d+\.\d+\.\d+\.\d+", settings[key])) == {"127.0.0.1"}
    assert int(settings["log.retention.hours"]) >= 24 * 365
    assert settings["log.retention.bytes"] == "-1"
    ports = re.findall(r":(\d+)", settings["listeners"])
    assert not {"8080", "8081", "8083", "8084"} & set(ports)


def test_script_has_every_action():
    """The script exists and handles the actions the README names."""
    script = (ROOT / "scripts" / "kafka-local.ps1").read_text(encoding="utf-8")
    for action in ("init", "start", "stop", "status", "topics"):
        assert f"'{action}'" in script
    assert "--if-not-exists" in script and "taskkill /T /F" in script


def test_readme_commands_name_existing_files_and_caveats():
    """Every script or config path in the README exists; the Windows and EC2 caveats are stated."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    paths = set(re.findall(r"(?:scripts|config)/[\w./-]+\.(?:ps1|properties)", readme))
    assert {"scripts/kafka-local.ps1", "config/kafka/server.properties"} <= paths
    for path in paths:
        assert (ROOT / path).is_file(), path
    assert "not officially supported" in readme
    assert "EC2" in readme and "UNVERIFIED" in readme
