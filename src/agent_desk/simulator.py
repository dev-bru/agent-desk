"""Publish a repeatable sample of labeled fictional support tickets."""

from datetime import datetime, timezone
from pathlib import Path
import random
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from agent_desk.messages import TicketCreated, TicketCreatedEnvelope, TicketTriaged
from agent_desk.telemetry import log_event, message_headers, ticket_span


class LabeledTicket(TicketTriaged):
    """Keep the expected triage labels beside each fictional ticket."""

    ticket_id: str = Field(min_length=1)


def load_tickets(path: str | Path = "data/tickets.jsonl") -> list[LabeledTicket]:
    """Read and check the labeled set before publishing anything."""
    tickets = [LabeledTicket.model_validate_json(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if not tickets or len({ticket.ticket_id for ticket in tickets}) != len(tickets):
        raise ValueError("Ticket set must be nonempty with unique ticket_id values")
    return tickets


def ticket_message(ticket: LabeledTicket) -> TicketCreatedEnvelope:
    """Make a wire ticket without exposing its expected labels to the model."""
    return TicketCreatedEnvelope(
        message_id=uuid5(NAMESPACE_URL, f"agent-desk:{ticket.ticket_id}:created"),
        ticket_id=ticket.ticket_id, created_at=datetime.now(timezone.utc), type="ticket.created",
        payload=TicketCreated(**ticket.model_dump(exclude={"category", "priority", "ticket_id"})),
    )


def simulate(bus, *, count: int = 40, seed: int = 0, poison: int = 0, duplicate: int = 0,
             path: str | Path = "data/tickets.jsonl") -> int:
    """Publish shuffled tickets, then exact repeats and malformed messages."""
    tickets = load_tickets(path)
    if not 0 <= count <= len(tickets) or poison < 0 or not 0 <= duplicate <= count:
        raise ValueError("count must fit the set; poison must be nonnegative; duplicate must fit count")
    selected = random.Random(seed).sample(tickets, count)
    sent = []
    for ticket in selected:
        message = ticket_message(ticket)
        with ticket_span("simulate", ticket.ticket_id, "desk.tickets"):
            headers = message_headers(ticket.ticket_id, "triage")
            bus.publish("desk.tickets", ticket.ticket_id, message.model_dump_json().encode("utf-8"), headers)
            log_event("simulate", ticket.ticket_id, str(message.message_id), 1, "published")
        sent.append((message, headers))
    for message, headers in sent[:duplicate]:
        with ticket_span("simulate", message.ticket_id, "desk.tickets", headers):
            bus.publish("desk.tickets", message.ticket_id, message.model_dump_json().encode("utf-8"),
                        message_headers(message.ticket_id, "triage"))
            log_event("simulate", message.ticket_id, str(message.message_id), 1, "duplicate_published")
    for index in range(poison):
        ticket_id = f"poison-{index}"
        with ticket_span("simulate", ticket_id, "desk.tickets"):
            bus.publish("desk.tickets", ticket_id, b'{"type":"ticket.created"}', message_headers(ticket_id, "triage"))
            log_event("simulate", ticket_id, "", 1, "poison_published")
    return count + duplicate + poison
