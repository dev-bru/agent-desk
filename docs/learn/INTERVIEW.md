# Interview pack: Agent Desk

Numbers below are MEASURED on this PC on 2026-11-02 unless marked otherwise.

## The story (STAR)

**Situation.** A fictional online shop gets support tickets. Refunds move money, models are probabilistic, and the
process can crash at any time. I wanted to show I can build agents that are safe to run, not only agents that work
once in a demo.

**Task.** Build an event-driven support desk: tickets flow through topics; a triage agent and a resolver agent are
consumers; the shop's tools sit behind MCP. Requirements: no lost tickets, no double refund, bad input must not
block the line, and every test must run offline.

**Action.**
- Put the work on a bus with a small interface and an in-memory fake that copies the broker rules that matter (key
  order, groups, commit after handle). Kafka is the planned second implementation.
- Wrote one `Runner` that wraps every handler: parse, build the key `<ticket>:<stage>`, run the handler and the key
  insert in one SQLite transaction, retry with exponential backoff and jitter, dead-letter with reason headers,
  commit last.
- Made the money step idempotent at three layers: handled store, fixed result message id, unique key in the refund
  tool.
- Used a strict Pydantic contract for every message and every model reply; one repair prompt, then fail.
- Built the resolver as a LangGraph graph with a SQLite checkpointer, a model-call cap (8), and code checks around
  every model decision. Proved resume with a test that stops after `gather` and restarts from the file.
- Exposed the shop through a FastMCP server over stdio; errors are MCP error results, not crashes.

**Result.**
- 79 offline tests pass in about 32 s with no broker, no model and no network (MEASURED).
- 6 of 11 planned features are passing (F-001 to F-006); approval flow, tracing, simulator, Kafka and lessons are
  still to do (feature_list.json).
- Specific proofs: retry delays are exactly `[2.2, 4.2]` for base 2 with injected jitter
  (`tests/test_runner.py:51`); a failed commit followed by redelivery runs the handler once
  (`tests/test_runner.py:22`); a restart after `gather` makes 0 repeat MCP reads and the run ends with
  `model_calls == 2` (`tests/test_resolver.py:87`); a failed commit and a re-sent ticket give 1 refund row
  (`tests/test_resolver.py:119`).
- About 1,100 lines of source and 1,070 lines of tests (line counts, MEASURED with `wc -l`).

## Tradeoffs I can defend

| Choice | Why | Cost |
|---|---|---|
| At-least-once plus idempotency, no exactly-once claim | Honest and provable; exactly-once across broker and DB is hard | Every consumer needs a key and care |
| Commit offset last | Crash means redelivery, not loss | Duplicates are possible |
| Handled key in the same SQLite transaction as the effect | Atomic: effect and key together | Only covers effects inside that database; a publish is outside it (known gap) |
| Own 15-line retry loop | Lesson stays visible; injected clock makes tests exact | No circuit breaker, no per-error policy |
| MemoryBus first, Kafka later | Logic proven without a broker | The fake can drift from Kafka; Kafka tests are opt-in |
| LLM proposes, code decides | Limits blast radius of a wrong or injected answer | More code and more rejection paths |
| LangGraph + SQLite checkpointer | Resume and (later) human pause with no extra service | SQLite is single-writer; not for many resolver processes |
| MCP over stdio | No port, easy local test | New process per call (`mcp_client.py:38` shortcut) |
| JSON + Pydantic, no schema registry | Small demo | No schema evolution rules |

## What I would do in production

- Real Kafka cluster (managed or 3+ brokers), replication factor 3, `min.insync.replicas=2`, producer
  `acks=all`, idempotent producer on. (General Kafka practice, UNVERIFIED here.)
- Transactional outbox or Kafka transactions for "write DB and publish" so the gap is closed; keep idempotent
  consumers anyway.
- Postgres for the handled store and checkpoints; one writer per partition-owner; leader-aware consumers.
- Schema registry with compatibility checks.
- Metrics and alerts: consumer lag, DLQ depth and age, retry rate, model latency and error rate, refund total per
  hour. Traces across hops (F-008 is planned).
- Retry policy per error class, a circuit breaker for the model, a bounded DLQ replay tool with audit log.
- Evals for triage on a labeled set with a regression gate in CI (F-009 planned).
- Authentication and per-tool authorization on the MCP server; an approval workflow with expiry for large refunds
  (F-007 planned).
- Secrets from a secrets manager; PII handling and retention for ticket text.

## Questions to be ready for

1. *Walk me through what happens when the process dies after the refund but before the commit.* Redelivery; the
   handled store has no key (the transaction did not finish) so the handler runs again; the `issue_refund` tool sees
   `T-1:refund` and returns the same refund. One row. (`shop_db.py:86`, test `tests/test_resolver.py:119`)
2. *Why not exactly-once?* Kafka transactions cover Kafka-to-Kafka. Our effects are in SQLite and a tool. We make
   effects idempotent instead.
3. *How do you stop a prompt injection from refunding money?* Ticket text is data; model amount is checked against
   order total and the auto limit in code; over-limit goes to a human (stub today, F-007); the refund tool is
   idempotent and checks the remaining balance.
4. *What happens if the model returns bad JSON?* One repair prompt; second failure raises; the runner retries the
   whole handler up to 3 times; then dead letter.
5. *How does the graph resume?* Thread id = ticket id; `get_state` shows saved values and a pending next node; we
   call `invoke(None, config)`.
6. *What is not built?* Say it plainly: approval flow, tracing, simulator and evals, KafkaBus. The pack marks them.
