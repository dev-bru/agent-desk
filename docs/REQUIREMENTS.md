# Agent Desk: requirements

Status: draft for the SPEC GATE (2026-11-02). Priority: M = must, S = should.
Source: I = idea.md, H = harness rule, A = assumption (confirm at gate).

## Shared definitions
- **Bus**: the interface `agent_desk.bus.Bus` with `publish(topic, key, value, headers)` and
  `consume(topics, group)`. Two classes implement it: `MemoryBus` (tests, lessons) and `KafkaBus` (real broker).
- **Envelope**: every message is JSON with `message_id`, `ticket_id`, `type`, `created_at`, `payload`. Trace context
  and `attempt` travel in headers. Schemas: ARCHITECTURE.md.
- **Idempotency key**: `ticket_id` + `stage` (for example `T-100:triage`). A consumer records handled keys in a
  SQLite table. A repeated key is skipped and acknowledged.
- **Scripted model**: `agent_desk.fakes.ScriptedModel(script)`. Same `chat()` signature as the real model. Replies
  from a JSON list in order. Records requests. A finished script raises `ScriptExhausted`.
- **Refund limit**: setting `refund_limit` (default 50.00). A refund above it needs human approval.
- **Offline**: no Kafka, no model server, no network. A socket guard in `conftest.py` blocks all non-loopback
  connects and all connects to the Kafka port.

## Foundation
**REQ-001 (M, H) Project setup.** Python 3.12, uv, package `agent_desk` under `src/`, console script `agent-desk`.
Runtime dependencies are exact pins (`==`). `uv.lock` holds hashes. `tzdata` is a dependency.
- AC1: `uv sync --locked` succeeds on a fresh clone.
- AC2: a test parses `pyproject.toml`: every runtime dependency uses `==`.
- AC3: `uv run agent-desk --help` lists `simulate`, `run`, `approve` and `eval`.

**REQ-002 (M, H) Settings, no secrets in files.** `agent-desk.toml` (example committed as
`agent-desk.example.toml`) holds: `bootstrap` (`localhost:9092`), `refund_limit` (50.00), `max_attempts` (3),
`backoff_base_s` (1.0), `model` (LiteLLM model string), `api_base` (optional), `db_path`, `checkpoint_path`.
Env vars `AGENT_DESK_<KEY>` override the file. Provider keys are read from the env only.
- AC1: a test loads the example file and gets the defaults above.
- AC2: `AGENT_DESK_REFUND_LIMIT=10` gives 10.0. A bad number gives an error naming the key.
- AC3: a test scans `src`, `tests`, `lessons` and the example file for key-like strings and user paths. It finds none.

**REQ-003 (M, I) Local Kafka broker on Windows (no Docker).** `scripts/kafka-local.ps1` (`start`, `stop`, `status`)
runs one Apache Kafka broker in KRaft mode from the binary distribution, with Java 21 (Temurin JDK). Versions pinned
at setup. Listener `127.0.0.1:9092`. Retention is set high for demos. The README states that Kafka does not
officially support Windows for production, that long runs can hit log-deletion file-lock errors, and gives the remote
EC2 Kafka fallback (UNVERIFIED). The topics from ARCHITECTURE.md are created by `agent-desk topics create`.
- AC1: an offline test reads the broker config template: KRaft settings present (`process.roles`, `node.id`,
  controller quorum), no ZooKeeper settings, listener bound to `127.0.0.1`, retention above the demo length; and
  checks the script exists and every README command names an existing file.
- AC2: (kafka-marked) with the broker started and `AGENT_DESK_KAFKA_BOOTSTRAP` set, `agent-desk topics create` makes
  every topic; running it twice succeeds.

## Bus and messages
**REQ-010 (M, I) Bus interface and memory fake.** `MemoryBus` keeps ordered logs per topic, per-key ordering, and
consumer groups with committed offsets.
- AC1: messages with the same key are read in publish order.
- AC2: two consumers in one group share the messages with no overlap. Two groups each get all messages.
- AC3: a message is redelivered if the consumer did not commit. A committed message is not redelivered.

**REQ-011 (M, I) Kafka bus.** `KafkaBus` implements `Bus` on the chosen client library. It commits offsets only
after the handler returns (at-least-once). Headers are carried unchanged.
- AC1: (kafka-marked) publish then consume returns the same key, value and headers.
- AC2: (kafka-marked) a handler that raises leaves the offset uncommitted; the message is redelivered after restart.
- AC3: an offline test with a fake client checks that commit happens after the handler, never before.

**REQ-012 (M, I) Message schemas.** Pydantic models for each topic's envelope and payload. Invalid JSON or schema
errors raise `BadMessage`.
- AC1: each model round-trips to and from JSON.
- AC2: a missing field or wrong type raises `BadMessage` naming the field.

**REQ-013 (M, I) Ticket simulator.** `agent-desk simulate` publishes tickets from a seeded labeled set
(`data/tickets.jsonl`, at least 40 tickets with label and priority). Options: `--count`, `--seed`, `--poison N`
(adds N malformed messages), `--duplicate N` (re-sends N tickets with the same id).
- AC1: the same seed gives the same ticket order.
- AC2: each ticket has an id, customer id, text, and an order id when relevant.
- AC3: `--poison 2` adds 2 messages that fail schema checks. `--duplicate 2` re-sends 2 ids.

## Reliability
**REQ-020 (M, I) Idempotent consumers.** A `Handled` store (SQLite) records `(consumer, idempotency_key)`.
- AC1: the same message handled twice runs the handler once and returns success both times.
- AC2: the key is written in the same transaction as the handler's own database write.
- AC3: a restart keeps the store (file-backed).

**REQ-021 (M, I) Retries with backoff.** A failing handler is retried up to `max_attempts` with delay
`backoff_base_s * 2^(attempt-1)` plus jitter. The test clock is injectable (no real sleeping in tests).
- AC1: a handler that fails twice then succeeds is called three times.
- AC2: delays follow the formula (jitter within a stated bound).
- AC3: `attempt` is carried in a header and logged.

**REQ-022 (M, I) Dead-letter handling.** After the last attempt, or at once for `BadMessage`, the original message
is published to `desk.dead-letter` with headers `dlq-reason`, `dlq-source-topic`, `dlq-attempts`. The offset is then
committed. `agent-desk dlq list|replay` shows and replays them.
- AC1: a poison message ends on the dead-letter topic after 0 retries. A transient failure after `max_attempts`.
- AC2: the consumer keeps running and handles the next message.
- AC3: `dlq replay` republishes to the source topic and the message is handled when the cause is fixed.

**REQ-023 (M, I) No exactly-once claim.** README and lesson 06 explain at-least-once plus idempotent consumers.
- AC1: a test greps docs and lessons: the words "exactly-once" appear only in a sentence that denies the claim
  (the sentence contains "not").

## Agents
**REQ-030 (M, I) LLM client on LiteLLM.** `model.chat(messages, tools=None)` calls `litellm.completion` with the
configured model string. Provider keys come from env. Errors become `ModelDown`, `ModelTimeout`, `ModelError`.
- AC1: a test with a patched `litellm.completion` checks the model string, api_base and timeout are passed.
- AC2: a missing key for a keyed provider gives an error naming the env var (never the value).
- AC3: connection errors, timeouts and HTTP 4xx map to the three errors.

**REQ-031 (M, I) Triage agent.** Consumes `desk.tickets`. Asks the model for JSON: `category` (one of `refund`,
`order_status`, `shipping`, `product`, `other`) and `priority` (`low`, `normal`, `high`). Publishes a `work` message
to `desk.work`.
- AC1: with the scripted model, a ticket yields the scripted category and priority.
- AC2: invalid model output is retried once with a repair prompt, then raises (and so is retried or dead-lettered).
- AC3: the consumer is idempotent (REQ-020).

**REQ-032 (M, I) Shop MCP server.** FastMCP server (stdio) over a seeded SQLite DB (`data/shop.sqlite` is built by
`agent-desk seed`). Tools: `lookup_order(order_id)`, `shipment_status(order_id)`, `refund_policy(category)`,
`issue_refund(order_id, amount, idempotency_key)`.
- AC1: each tool returns the seeded data for a known id.
- AC2: an unknown id returns an error result (`isError`) that names the id. No exception leaves the server.
- AC3: `issue_refund` with the same key twice refunds once.

**REQ-033 (M, I) Resolver graph.** LangGraph graph with nodes `plan`, `gather` (MCP tool calls), `decide`,
`await_approval`, `act`, `reply`. State is checkpointed with a SQLite checkpointer, thread id = ticket id.
- AC1: with scripted model and an in-process shop, a status ticket reaches `reply` with no approval step.
- AC2: a refund at or below the limit goes `decide` -> `act` -> `reply`.
- AC3: a step limit (default 8 model calls) stops the graph with a clear message.
- AC4: a graph run killed after `gather` and restarted from the same checkpoint file does not repeat `gather`.

**REQ-034 (M, I) Human approval.** For a refund above the limit, the graph publishes an `approval.request` to
`desk.approvals.requests` and stops (LangGraph `interrupt`). The resolver resumes when an `approval.decision` for
that ticket arrives on `desk.approvals.decisions`.
- AC1: approve -> the refund is issued once and the reply says so.
- AC2: reject -> no refund; the reply says the refund was declined, with the reviewer note.
- AC3: no decision does not block other tickets (the consumer keeps handling them).
- AC4: a duplicate decision does nothing.
- AC5: the resolver restarted between request and decision still resumes correctly.

**REQ-035 (M, I) Approver tools.** `agent-desk approve` lists pending requests and approves or rejects in the
terminal. `agent-desk approve --web` serves one local page (127.0.0.1) with the same actions.
- AC1: CLI approve publishes a decision message with reviewer name and note.
- AC2: the web page lists pending requests and posts decisions. It binds to 127.0.0.1 only.
- AC3: tests use `MemoryBus` and make no network calls beyond loopback.

**REQ-036 (M, I) Results.** The resolver publishes a `result` to `desk.results`: final status
(`resolved`, `refunded`, `declined`, `escalated`), reply text, refund amount, steps taken.
- AC1: every ticket that is not dead-lettered gets exactly one result per idempotency key.
- AC2: `agent-desk results` prints a table of results.

## Observability
**REQ-040 (M, I) Structured logs.** One JSON line per event with `ts`, `level`, `component`, `ticket_id`,
`message_id`, `trace_id`, `attempt`, `event`.
- AC1: a test captures logs for one ticket and finds the fields on every line.
- AC2: logs never contain an API key value.

**REQ-041 (M, I) Traces across Kafka hops.** OpenTelemetry. The producer injects W3C `traceparent` into message
headers. Each consumer extracts it and starts a child span. Spans go to a console or file exporter by default.
- AC1: with the memory bus, the spans of one ticket (simulate, triage, resolve, approve) share one trace id.
- AC2: each span has `ticket_id` and `topic` attributes.
- AC3: the OTLP exporter is optional and off by default.

## Evals
**REQ-050 (M, I) Triage eval.** `agent-desk eval triage` runs the triage agent over the labeled set and prints
accuracy for category and priority, plus a confusion table. `--fake` uses the scripted model.
- AC1: with a script that copies the labels, accuracy is 1.0.
- AC2: with a script that gets one wrong, accuracy is (n-1)/n and the confusion table shows the cell.
- AC3: results are written to `runs/eval-<time>.json` with model name and set size.

## Teaching
**REQ-060 (M, I) Comments.** Every module and public function has plain-English comments (eli5, ASD-STE100).
- AC1: a test checks each `src/agent_desk/*.py` has a module docstring and every public function has a docstring.

**REQ-061 (M, I) Lessons.** `lessons/` holds six lessons, each a markdown file and a runnable script on the
memory bus: 01 event basics, 02 consumer groups, 03 agent as consumer, 04 graph state, 05 approvals, 06 failures.
- AC1: each script runs offline with `--fake` and exits 0.
- AC2: each lesson names the concept, the command, the expected output and the source files to read.

**REQ-062 (S, I) Architecture diagram.** An interactive HTML diagram of the flows (happy path, approval, retry and
dead letter). Built after phase 2 with the architecture-diagram skill.
- AC1: the file opens offline and shows all topics and agents.

## Opt-in tests
**REQ-070 (M, H) Test markers.** `kafka` and `live` markers are registered. The default run deselects them. Kafka
tests also need the env var `AGENT_DESK_KAFKA_BOOTSTRAP` (the bootstrap address, local or remote).
- AC1: default `uv run pytest` runs 0 kafka tests and 0 live tests.
- AC2: `pytest -m kafka` without the env var skips with one clear reason; with the env var but no broker it fails
  with one clear message (not a hang). Connect timeout 5 s.
