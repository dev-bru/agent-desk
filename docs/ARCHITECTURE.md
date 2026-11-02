# Agent Desk: architecture

Status: draft for the SPEC GATE (2026-11-02). REQUIREMENTS.md wins on any detail. The interactive diagram is built
after phase 2 (REQ-062).

## Stack
Versions are chosen at setup and logged in `docs/DEPENDENCIES.md`. Labels: DOCUMENTED needs URL and date at setup.
| Part | Chosen | Rejected (why) |
|---|---|---|
| Language | Python 3.12 via uv | Python 3.13 (less library support, UNVERIFIED) |
| Broker | Apache Kafka binary distribution run natively on Windows (Java 21 Temurin JDK), KRaft, one broker; dev only. Fallback: remote EC2 Kafka (UNVERIFIED) | Docker image (Docker unavailable, D-017); Redpanda (smaller and faster, but the learner should meet real Kafka; its tools differ); ZooKeeper mode (removed in Kafka 4, DOCUMENTED at setup) |
| Kafka client | confluent-kafka (librdkafka; Windows wheels, UNVERIFIED at setup) | kafka-python (slow upkeep); aiokafka (async adds a second concept to teach) |
| Agent framework | LangGraph with SQLite checkpointer | hand-written state machine (Agent Lab already did hand-written); Postgres checkpointer (one more container) |
| Tool protocol | MCP via FastMCP, stdio | HTTP transport (needs a port; nothing gained locally) |
| Model API | LiteLLM (one API; local Qwen or free Gemini, Groq, NVIDIA NIM) | raw provider SDKs (one provider each) |
| Local model | Qwen on llama.cpp `llama-server` (as in Agent Lab) | Ollama (not installed) |
| Messages | Pydantic models, JSON on the wire | Avro + schema registry (heavy for a one-broker demo) |
| Storage | SQLite files (shop data, handled keys, checkpoints) | Postgres (extra container, no gain here) |
| Tracing | OpenTelemetry SDK, console/file exporter, W3C traceparent in headers | vendor APM (cost, account) |
| Web approver | stdlib `http.server`, one page | Flask/FastAPI (a dependency for one page) |
| Tests | pytest + MemoryBus + ScriptedModel; kafka marker opt-in (needs `AGENT_DESK_KAFKA_BOOTSTRAP`) | real broker in every test (slow, needs a running broker) |

## Layout
```
agent-desk/
  pyproject.toml  uv.lock  agent-desk.example.toml  README.md
  scripts/         # kafka-local.ps1 (start/stop/status of the native broker), documented in README
  data/            # tickets.jsonl (labeled), shop seed data
  src/agent_desk/
    settings.py    # REQ-002
    messages.py    # REQ-012: envelope + payload models, BadMessage
    bus.py         # Bus protocol, MemoryBus (REQ-010)
    kafka_bus.py   # KafkaBus (REQ-011), topics create (REQ-003)
    runner.py      # consumer loop: idempotency, retry, backoff, DLQ (REQ-020..022)
    handled.py     # SQLite idempotency store
    model.py       # LiteLLM client (REQ-030)
    fakes.py       # ScriptedModel
    shop_db.py     # seed + queries
    mcp_server.py  # REQ-032: FastMCP shop server
    mcp_client.py  # opens the stdio session, lists and calls tools
    triage.py      # REQ-031
    resolver.py    # REQ-033/034/036: LangGraph graph
    approver.py    # REQ-035: CLI + web
    simulator.py   # REQ-013
    telemetry.py   # REQ-040/041
    evals.py       # REQ-050
    cli.py         # agent-desk simulate|run|approve|eval|topics|dlq|results|seed
  lessons/         # 01..06 (REQ-061)
  tests/           # offline; tests/kafka/ opt-in
```

## Components
- **Simulator** publishes tickets to `desk.tickets`.
- **Triage agent** (consumer group `triage`) reads tickets, calls the model, writes `work` to `desk.work`.
- **Resolver agent** (group `resolver`) reads `desk.work` and `desk.approvals.decisions`. It runs the LangGraph graph.
  The graph calls shop tools through the MCP client.
- **Shop MCP server** is a child process (stdio) that reads the seeded SQLite DB.
- **Approver** (CLI or web) reads `desk.approvals.requests`, writes decisions.
- **Runner** wraps every handler: skip handled keys, retry with backoff, dead-letter on failure, commit offset last.
- **Telemetry** injects and extracts trace context in headers, writes JSON logs.

## Flow (happy path)
1. Simulator -> `desk.tickets`.
2. Triage -> `desk.work` (category, priority).
3. Resolver graph: `plan` -> `gather` (MCP) -> `decide`.
4. If refund <= limit: `act` (MCP `issue_refund`) -> `reply` -> `desk.results`.
5. If refund > limit: publish to `desk.approvals.requests`, `interrupt`. On a decision: resume, then `act` or decline,
   then `reply`.
6. On failure: retry; after the limit -> `desk.dead-letter`.

## Topics
| Topic | Key | Producer | Consumer group | Message `type` |
|---|---|---|---|---|
| desk.tickets | ticket_id | simulator | triage | ticket.created |
| desk.work | ticket_id | triage | resolver | ticket.triaged |
| desk.approvals.requests | ticket_id | resolver | approver | approval.requested |
| desk.approvals.decisions | ticket_id | approver | resolver | approval.decided |
| desk.results | ticket_id | resolver | results viewer | ticket.resolved |
| desk.dead-letter | ticket_id | runner | dlq tool | (original message) |

One partition per topic by default. A setting raises it for lesson 02 (consumer groups). Keyed by `ticket_id`, so all
events of one ticket stay in order.

## Contracts

### Envelope (JSON value)
```
{ "message_id": "uuid", "ticket_id": "T-100", "type": "ticket.created",
  "created_at": "2026-11-02T10:00:00Z", "payload": { ... } }
```
Headers (bytes): `traceparent`, `attempt` (int as text), `idempotency-key`.
DLQ adds: `dlq-reason`, `dlq-source-topic`, `dlq-attempts`.

### Payloads
- ticket.created: `customer_id`, `text`, `order_id` (optional), `channel`.
- ticket.triaged: all of the above plus `category` (refund, order_status, shipping, product, other), `priority`
  (low, normal, high).
- approval.requested: `order_id`, `amount`, `reason`, `limit`.
- approval.decided: `approved` (bool), `reviewer`, `note`.
- ticket.resolved: `status` (resolved, refunded, declined, escalated), `reply`, `refund_amount` (optional), `steps`.

### Idempotency key
`<ticket_id>:<stage>`, stage in `triage`, `resolve`, `decision`. The refund tool takes `<ticket_id>:refund`.

### Shop MCP tools
- `lookup_order(order_id)` -> id, customer_id, items, total, status.
- `shipment_status(order_id)` -> carrier, state, eta.
- `refund_policy(category)` -> text, max_days, auto_limit.
- `issue_refund(order_id, amount, idempotency_key)` -> refund id. Repeat key returns the same refund.
Errors: `isError: true` with a message that says what was wrong and what is valid.

### Resolver graph state
`ticket_id`, `messages`, `order`, `shipment`, `policy`, `proposed_refund`, `approval`, `status`, `steps`.
Checkpoint thread id = `ticket_id`.

## Data
- `data/shop.sqlite` (built by `agent-desk seed`): customers, orders, shipments, refunds.
- `.agent-desk/handled.sqlite`: handled idempotency keys per consumer.
- `.agent-desk/checkpoints.sqlite`: LangGraph checkpoints.
- `data/tickets.jsonl`: labeled tickets, at least 40, committed. All fictional.
- `runs/`: eval results and trace files (gitignored).

## Hosting and network
- Development broker: Apache Kafka (binary distribution) on the Windows PC, KRaft, one node, listener bound to
  `127.0.0.1:9092`, started by `scripts/kafka-local.ps1`. Needs Java 21 (Temurin). No Docker (D-017).
- Kafka does not officially support Windows for production (DOCUMENTED at setup, URL and date). A long-running broker
  on Windows can hit file-lock errors when it deletes old log segments, so `log.retention` is set high for demos and
  the broker is stopped when idle. If it still fails, delete the log folder and restart.
- Fallback: a Kafka broker on a remote EC2 machine, reached through `AGENT_DESK_KAFKA_BOOTSTRAP` (UNVERIFIED; the
  guide is text only, agents create no cloud resource, and security rules must not open the port to the world).
- Tests use `MemoryBus` by default. Kafka tests run only when `AGENT_DESK_KAFKA_BOOTSTRAP` is set.

## Delivery model
At-least-once. The runner commits the offset after the handler succeeds. A crash between handler and commit causes
a redelivery. The idempotency store makes the repeat harmless. Exactly-once is not claimed (REQ-023). A known gap:
the Kafka publish and the database write cannot share one transaction. The design keeps each handler's effect
inside SQLite and publishes the next event after; a crash between them is repaired by the redelivery.

## Risks
| Risk | Mitigation |
|---|---|
| confluent-kafka has no Windows wheel for 3.12 (UNVERIFIED) | check at F-010 setup; fall back to a pinned alternative, log in DECISIONS |
| Kafka on Windows is not supported for production; log-segment deletion can hit file locks on long runs (UNVERIFIED on this PC) | dev only; high retention for demos; stop the broker when idle; remote EC2 Kafka as fallback; small heap setting |
| Java 21 and Kafka binary download size/setup on this PC (UNVERIFIED) | document exact steps in the README at F-010; human approves the installs |
| Small local Qwen gives bad JSON | repair prompt once; evals show it; free cloud models as option |
| Free-tier rate limits (Gemini, Groq, NIM) | backoff in LiteLLM calls; evals can run `--fake` |
| LangGraph `interrupt` plus checkpointer API changes between versions | pin exact version; test resume across process restart |
| Supply chain (LiteLLM had bad releases in 2026, UNVERIFIED detail) | exact pins, hashes in uv.lock, review before install |
| Scope too large | 11 features, two phases; Kafka last so the logic is proven offline first |
