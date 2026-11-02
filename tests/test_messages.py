"""Check every wire message and its validation errors."""

import json

import pytest

from agent_desk.messages import BadMessage, parse_message


PAYLOADS = {
    "ticket.created": {"customer_id": "C-1", "text": "Where is it?", "channel": "email"},
    "ticket.triaged": {"customer_id": "C-1", "text": "Where is it?", "channel": "email", "category": "shipping", "priority": "normal"},
    "approval.requested": {"order_id": "O-1", "amount": 75.0, "reason": "Broken", "limit": 50.0},
    "approval.decided": {"approved": True, "reviewer": "Demo", "note": "Approved"},
    "ticket.resolved": {"status": "resolved", "reply": "It is on the way", "steps": ["gather", "reply"]},
}


def wire(kind="ticket.created", payload=None):
    """Build a valid sample envelope with a replaceable payload."""
    return json.dumps({"message_id": "00000000-0000-0000-0000-000000000001", "ticket_id": "T-1", "type": kind, "created_at": "2026-11-02T10:00:00Z", "payload": PAYLOADS[kind] if payload is None else payload})


@pytest.mark.parametrize("kind", PAYLOADS)
def test_round_trip(kind):
    """Every payload and envelope survives a JSON round trip."""
    message = parse_message(wire(kind))
    assert parse_message(message.model_dump_json()) == message
    assert message.payload.model_validate_json(message.payload.model_dump_json()) == message.payload


@pytest.mark.parametrize("kind", PAYLOADS)
def test_missing_and_wrong_payload_fields(kind):
    """A missing field or wrong type names the bad field."""
    field = next(iter(PAYLOADS[kind]))
    for action in ("missing", "wrong"):
        payload = dict(PAYLOADS[kind])
        if action == "missing":
            del payload[field]
        else:
            payload[field] = ["wrong type"]
        with pytest.raises(BadMessage, match=field):
            parse_message(wire(kind, payload))


@pytest.mark.parametrize("field,value", [("message_id", "bad"), ("ticket_id", 10), ("created_at", "yesterday"), ("type", "unknown")])
def test_bad_envelope(field, value):
    """Envelope errors also identify the field."""
    data = json.loads(wire())
    data[field] = value
    with pytest.raises(BadMessage, match=field):
        parse_message(json.dumps(data))


def test_bad_json_and_strict_bool():
    """Malformed JSON and a text boolean cannot enter the desk."""
    with pytest.raises(BadMessage, match="JSON"):
        parse_message(b"{broken")
    payload = dict(PAYLOADS["approval.decided"], approved="false")
    with pytest.raises(BadMessage, match="approved"):
        parse_message(wire("approval.decided", payload))
