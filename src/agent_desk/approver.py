"""Show pending refunds and send human decisions through the bus."""

from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from secrets import token_urlsafe
from urllib.parse import parse_qs
from uuid import uuid4

from agent_desk.messages import ApprovalDecided, ApprovalDecidedEnvelope, ApprovalRequestedEnvelope, parse_message
from agent_desk.telemetry import log_event, message_headers, ticket_span


def read_topic(bus, topic):
    """Read a fresh view without moving another consumer's position."""
    # shortcut: Read the whole topic for this demo; store a view when logs grow.
    subscription = bus.consume([topic], f"view-{uuid4()}")
    records = []
    try:
        while (record := subscription.poll()) is not None:
            records.append(record)
            subscription.commit(record)
    finally:
        subscription.close()
    return records


def pending(bus):
    """Collapse repeated requests and hide tickets that already have a decision."""
    requests = {}
    for record in read_topic(bus, "desk.approvals.requests"):
        message = parse_message(record.value)
        if isinstance(message, ApprovalRequestedEnvelope):
            requests[message.ticket_id] = message
    for record in read_topic(bus, "desk.approvals.decisions"):
        message = parse_message(record.value)
        if isinstance(message, ApprovalDecidedEnvelope):
            requests.pop(message.ticket_id, None)
    return list(requests.values())


def decide(bus, ticket_id: str, approved: bool, reviewer: str, note: str = ""):
    """Publish a checked decision for a pending ticket."""
    if not reviewer.strip():
        raise ValueError("reviewer must not be empty")
    request = next((item for item in pending(bus) if item.ticket_id == ticket_id), None)
    if request is None:
        raise ValueError("ticket_id has no pending approval")
    message = ApprovalDecidedEnvelope(
        message_id=uuid4(), ticket_id=ticket_id, created_at=datetime.now(timezone.utc),
        type="approval.decided", payload=ApprovalDecided(approved=approved, reviewer=reviewer, note=note),
    )
    record = next(record for record in read_topic(bus, "desk.approvals.requests") if record.key == ticket_id)
    with ticket_span("approve", ticket_id, "desk.approvals.decisions", record.headers):
        bus.publish("desk.approvals.decisions", ticket_id, message.model_dump_json().encode("utf-8"),
                    message_headers(ticket_id, "decision"))
        log_event("approve", ticket_id, str(message.message_id), 1, "decision_sent")
    return message


def create_web_server(bus, port: int = 0) -> HTTPServer:
    """Make one local approval page on the IPv4 loopback address only."""
    token = token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        """Serve forms and check local form submissions."""

        def do_GET(self):
            """List pending refunds with approve and reject buttons."""
            if self.path != "/":
                self.send_error(404)
                return
            forms = []
            for item in pending(bus):
                forms.append(
                    f'<form method="post"><p>{escape(item.ticket_id)}: {item.payload.amount:.2f} '
                    f'{escape(item.payload.reason)}</p><input type="hidden" name="ticket_id" '
                    f'value="{escape(item.ticket_id, quote=True)}">'
                    f'<input type="hidden" name="token" value="{token}">'
                    '<label>Reviewer <input name="reviewer" required></label>'
                    '<label>Note <input name="note"></label>'
                    '<button name="decision" value="approve">Approve</button>'
                    '<button name="decision" value="reject">Reject</button></form>'
                )
            body = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                    '<title>Refund approvals</title><h1>Pending refunds</h1>' +
                    ("".join(forms) or "<p>No pending refunds.</p>") + '</html>').encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            """Accept only the local page's form and publish its decision."""
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/" or not 0 < length <= 16384:
                    raise ValueError("Invalid form size or path")
                form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
                if form["token"] != [token] or form["decision"][0] not in {"approve", "reject"}:
                    raise ValueError("Invalid form token or decision")
                decide(bus, form["ticket_id"][0], form["decision"][0] == "approve",
                       form["reviewer"][0], form.get("note", [""])[0])
            except (ValueError, KeyError, UnicodeError):
                self.send_error(400, "Invalid or stale approval form")
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def log_message(self, format, *args):
            """Keep ticket text out of HTTP access logs."""

    return HTTPServer(("127.0.0.1", port), Handler)
