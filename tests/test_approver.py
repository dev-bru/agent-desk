"""Check terminal and loopback web decisions on the memory bus."""

from http.client import HTTPConnection
import re
from threading import Thread
from urllib.parse import urlencode

import pytest

from agent_desk.approver import create_web_server, decide, pending, read_topic
from agent_desk.bus import MemoryBus
from agent_desk.cli import main
from agent_desk.fakes import ScriptedModel
from agent_desk.messages import parse_message
from agent_desk.resolver import Resolver
from test_resolver import shop, work


@pytest.fixture
def waiting(shop):
    """Publish one real approval request from the resolver."""
    settings, tools = shop
    bus = MemoryBus()
    resolver = Resolver(bus, ScriptedModel([
        {"text": '{"action":"refund"}'}, {"text": '{"action":"refund","amount":75}'},
    ]), tools, settings)
    try:
        resolver.handle(work("refund", "O-2", "C-2"), None)
    finally:
        resolver.close()
    return bus


def test_cli_list_and_decide(waiting, capsys):
    """The terminal lists requests and publishes the reviewer's note."""
    assert main(["approve"], bus=waiting) == 0
    assert "T-1 75.00" in capsys.readouterr().out
    assert main(["approve", "T-1", "--reject", "--reviewer", "Sam", "--note", "Too late"], bus=waiting) == 0
    message = parse_message(read_topic(waiting, "desk.approvals.decisions")[0].value)
    assert message.payload.model_dump() == {"approved": False, "reviewer": "Sam", "note": "Too late"}
    assert pending(waiting) == []
    with pytest.raises(ValueError, match="pending"):
        decide(waiting, "T-1", True, "Sam")


def test_web_list_post_and_bind(waiting):
    """Only loopback is bound, and a valid page form sends a decision."""
    server = create_web_server(waiting)
    assert server.server_address[0] == "127.0.0.1"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        client.request("GET", "/")
        response = client.getresponse()
        page = response.read().decode()
        assert response.status == 200 and "T-1" in page and "75.00" in page
        token = re.search('name="token" value="([^"]+)"', page)[1]
        for form_token, expected in [("bad", 400), (token, 303)]:
            client.request("POST", "/", urlencode({"token": form_token, "ticket_id": "T-1",
                           "reviewer": "Sam", "note": "Checked", "decision": "approve"}),
                           {"Content-Type": "application/x-www-form-urlencoded"})
            response = client.getresponse()
            response.read()
            assert response.status == expected
        assert parse_message(read_topic(waiting, "desk.approvals.decisions")[0].value).payload.approved
        assert pending(waiting) == []
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(5)
