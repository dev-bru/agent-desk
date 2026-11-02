# Agent Desk: decisions

Each entry: what, who decided, why. Labels: MEASURED (on this PC), DOCUMENTED (URL + date), UNVERIFIED.
ASSUMPTION entries are Claude's defaults; the human confirms or changes them at the SPEC GATE.

## D-001 Event-driven design with Kafka (human, idea)
The goal is to show Kafka skills. Tickets, work, approvals and results are events. Agents are consumers.

## D-002 Apache Kafka in KRaft mode, one broker (ASSUMPTION)
Real Kafka is the skill employers name. KRaft needs no ZooKeeper, so one process is enough. Redpanda starts faster
and uses less memory, but speaks only the Kafka API, and its tools differ. Switch to Redpanda if native Kafka is
too heavy or unstable on Windows (UNVERIFIED on this PC; measure at F-010). Runs natively, not in Docker (D-017).

## D-003 At-least-once plus idempotent consumers; exactly-once is not claimed (human, idea)
Exactly-once across Kafka and an external database is not claimed here. The honest design is
at-least-once with idempotency keys. The docs explain why.

## D-004 Bus interface with a memory fake (ASSUMPTION)
Offline tests and lessons need no broker. `MemoryBus` and `KafkaBus` share one small interface. Reason: tests stay
fast and the Kafka layer stays thin. The fake must copy the rules that matter: key order, groups, commit after handle.

## D-005 Resolver is a LangGraph graph with a SQLite checkpointer (human, idea)
Durable state and `interrupt` are the advanced LangGraph skills to show. SQLite needs no container.
Postgres is a later option, not a need.

## D-006 Approval through two topics and `interrupt` (ASSUMPTION)
The graph publishes a request, stops, and the resolver consumer resumes it when the decision arrives. The resolver
never blocks on a human, so other tickets keep flowing.

## D-007 Shop tools through own FastMCP server, stdio (human, idea; same choice as Agent Lab)
Order lookup, refund policy, shipment status, refund. Data in a seeded SQLite file.

## D-008 LLM through LiteLLM; provider by setting; keys only from env (human, idea)
Local Qwen (llama-server) or free Gemini, Groq, NVIDIA NIM. Env vars GEMINI_API_KEY, GROQ_API_KEY,
NVIDIA_NIM_API_KEY. Never in files, logs or tests.

## D-009 Python 3.12 via uv; exact pins with hashes (harness default)
All versions chosen at setup after a PyPI check. No version is guessed in these documents.

## D-010 Own retry loop in the runner, no retry library (ASSUMPTION, ponytail rule)
The loop is about 20 lines: attempt, sleep with backoff and jitter, give up. A library hides the lesson.

## D-011 Dead-letter topic with reason headers and a replay command (ASSUMPTION)
Operators need to see why a message failed and to retry it. Headers carry the facts. The message body stays the
original.

## D-012 Stdlib web approver (ASSUMPTION)
One page, three actions. `http.server` is enough. Bind to 127.0.0.1 only.

## D-013 Offline first: Kafka layer comes last (ASSUMPTION)
Phase 1 builds and proves all logic on `MemoryBus`. Phase 2 adds Kafka, tracing across hops, evals and lessons.
Reason: failures in the logic are cheaper to find without a broker.

## D-014 Messages are JSON with Pydantic models, no schema registry (ASSUMPTION)
A registry is another service. Pydantic models give the same checks for a demo. The Risks section notes Avro as a
production step.

## D-015 OpenTelemetry with console/file exporter by default (ASSUMPTION)
No account or collector needed. OTLP export is optional. Trace context travels as W3C `traceparent` in Kafka headers.

## D-016 Fictional shop, synthetic data only (human, idea)
No real customers or orders. Not hiring, assessment or edtech.

## D-017 No Docker: local services (human, 2026-11-02)
Docker is not available on this Windows PC (no virtualization). Nothing in this project needs Docker or Compose.
Kafka runs natively for development: Java 21 Temurin JDK plus the Apache Kafka binary distribution in KRaft mode,
started by a documented PowerShell script. Kafka does not officially support Windows for production, and a
long-running broker on Windows can hit log-deletion file-lock errors, so retention is set high for demos and the
broker is stopped when idle. Fallback: a remote EC2 Kafka (UNVERIFIED; no resource created by agents). The in-memory
bus stays the default for tests; Kafka tests stay opt-in through `AGENT_DESK_KAFKA_BOOTSTRAP`.
