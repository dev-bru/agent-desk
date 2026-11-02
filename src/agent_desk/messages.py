"""Check the JSON envelopes and payloads carried by desk topics."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class BadMessage(ValueError):
    """Report a message that cannot be read safely."""


class Payload(BaseModel):
    """Reject extra fields and values with the wrong type."""

    model_config = ConfigDict(extra="forbid", strict=True)


class TicketCreated(Payload):
    """Describe the customer's request."""

    customer_id: str
    text: str
    order_id: str | None = None
    channel: str


class TicketTriaged(TicketCreated):
    """Add the category and urgency chosen by triage."""

    category: Literal["refund", "order_status", "shipping", "product", "other"]
    priority: Literal["low", "normal", "high"]


class ApprovalRequested(Payload):
    """Ask a human to review a refund."""

    order_id: str
    amount: float = Field(ge=0, allow_inf_nan=False)
    reason: str
    limit: float = Field(ge=0, allow_inf_nan=False)


class ApprovalDecided(Payload):
    """Record the human's answer and note."""

    approved: bool
    reviewer: str
    note: str


class TicketResolved(Payload):
    """Describe the final answer and the steps taken."""

    status: Literal["resolved", "refunded", "declined", "escalated"]
    reply: str
    refund_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    steps: list[str]


class Envelope(BaseModel):
    """Keep the common fields for all valid desk events."""

    model_config = ConfigDict(extra="forbid")
    message_id: UUID
    ticket_id: str = Field(strict=True)
    created_at: AwareDatetime


class TicketCreatedEnvelope(Envelope):
    """Carry a new ticket."""

    type: Literal["ticket.created"]
    payload: TicketCreated


class TicketTriagedEnvelope(Envelope):
    """Carry a ticket ready for the resolver."""

    type: Literal["ticket.triaged"]
    payload: TicketTriaged


class ApprovalRequestedEnvelope(Envelope):
    """Carry a pending refund review."""

    type: Literal["approval.requested"]
    payload: ApprovalRequested


class ApprovalDecidedEnvelope(Envelope):
    """Carry a completed refund review."""

    type: Literal["approval.decided"]
    payload: ApprovalDecided


class TicketResolvedEnvelope(Envelope):
    """Carry a ticket result."""

    type: Literal["ticket.resolved"]
    payload: TicketResolved


Message = Annotated[
    TicketCreatedEnvelope | TicketTriagedEnvelope | ApprovalRequestedEnvelope
    | ApprovalDecidedEnvelope | TicketResolvedEnvelope,
    Field(discriminator="type"),
]
_adapter = TypeAdapter(Message)


def parse_message(value: str | bytes) -> Message:
    """Read wire JSON or raise BadMessage with the invalid field names."""
    try:
        return _adapter.validate_json(value)
    except ValidationError as exc:
        fields = [".".join(map(str, error["loc"])) or "type or JSON" for error in exc.errors()]
        raise BadMessage(f"Invalid message field: {', '.join(fields)}") from None
