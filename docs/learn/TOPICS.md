# Topics: concept map

Each topic: what it is (eli5), why industry uses it, where it lives here, what we did not pick, common mistakes,
two interview questions. Line numbers were checked on 2026-11-02 against the current files.

---

## 1. Event-driven architecture and a message bus

- **eli5.** Instead of one worker calling the next ("hey triage, do this"), each worker drops a note in a box
  ("a ticket was created"). Anyone who cares reads the box. Workers do not know each other.
- **Why industry uses it.** Producers and consumers fail, scale and deploy on their own. The box keeps messages
  while a worker is down. New consumers can be added without touching the producer.
- **Here.** `Bus` and `Consumer` protocols `bus.py:19-45`; in-process `MemoryBus` `bus.py:47`; event types
  `messages.py:70-102`.
- **Not picked.** Direct function calls or HTTP between agents: simpler, but a crash loses the work and every
  caller must know every callee.
- **Mistakes.** Treating events as commands with a hidden reply; putting huge payloads in events; forgetting that
  order exists only per key.
- **Q1.** *Event vs command?* An event says something happened (past tense, many listeners); a command asks one
  actor to do something.
- **Q2.** *Cost of event-driven?* Harder debugging (no call stack), eventual consistency, duplicates to handle.

## 2. Topics, keys, partitions, consumer groups

- **eli5.** A topic is a labeled log (a roll of paper you only add to). The key decides which lane a note goes in,
  so notes with the same key stay in order. A group is a team: team members share the work; two teams each get
  every note.
- **Why.** Ordering where it matters (one ticket) and parallelism where it does not (many tickets).
- **Here.** Key = `ticket_id` (`triage.py:61`). `MemoryBus.poll` blocks a key while an earlier record of that key
  is claimed (`bus.py:87-95`). Tests: `tests/test_memory_bus.py:8` (order), `:23` (groups).
- **Not picked.** One global queue: no ordering per ticket under parallel workers.
- **Mistakes.** Expecting order across keys; using a random key; more consumers than partitions (idle ones).
- **Q1.** *How does Kafka keep one ticket in order?* Same key, same partition; a partition has one consumer in a
  group at a time.
- **Q2.** *Two services both need every ticket?* Give them different consumer groups.

## 3. Why Kafka (and why not yet)

- **eli5.** Kafka is a very sturdy, very fast "box" that keeps notes on disk for days and lets many teams read at
  their own speed.
- **Why industry uses it.** Durable replayable log, high throughput, partitioned ordering, a big ecosystem.
  (General knowledge; the short runs on this PC are MEASURED, see section 14.)
- **Here.** `KafkaBus` `kafka_bus.py:50` (F-010, built). `MemoryBus` copies the rules that matter so the logic is proven
  first (decision D-004, D-013 in `docs/DECISIONS.md`). Kafka on Windows is dev only (D-017).
- **Not picked.** Redpanda (D-002), RabbitMQ or SQS (no replayable log by default; UNVERIFIED detail), Avro and a
  schema registry (D-014).
- **Mistakes.** Using Kafka for a tiny single-process job; exactly-once is not claimed here.
- **Q1.** *Kafka vs a queue?* Kafka keeps a log you can re-read; a classic queue deletes a message when acked.
- **Q2.** *Why a fake bus?* Fast offline tests; the interface stays small; Kafka is a thin adapter.

## 4. At-least-once delivery

- **eli5.** "I will keep delivering until you tell me you finished." If you finish but your thank-you is lost, I
  deliver again. You may see a note twice, never zero times.
- **Why.** The honest choice: no lost work. Exactly-once across a broker and a database is not claimed here.
- **Here.** Commit after the handler: `runner.py:68`. `MemoryBus` claims a record and only `commit` marks it done
  (`bus.py:101`); `close` releases it (`bus.py:110`). Test: `tests/test_memory_bus.py:45`;
  `tests/test_runner.py:22` fails the commit and checks the redelivery does the work once.
- **Not picked.** At-most-once (commit first; a crash loses work). Exactly-once is not claimed (D-003).
- **Mistakes.** Commit before the work; do not claim "exactly-once" for effects outside the broker.
- **Q1.** *Where can duplicates come from?* Crash between handler and commit; consumer rebalance; replay.
- **Q2.** *Why commit last?* A crash before the commit means redelivery (safe); after means loss (unsafe).

## 5. Idempotent consumers

- **eli5.** Pressing an elevator button twice does not call two elevators. Doing the same job twice leaves the
  same result as once.
- **Why.** At-least-once is only safe if repeats are harmless.
- **Here.** Three layers. (1) `Handled.run` stores `(consumer, key)` in the same SQLite transaction as the handler
  writes (`handled.py:21-36`). (2) Resolver result has a fixed UUID5 message id (`resolver.py:161`). (3) The refund
  tool: `refunds.idempotency_key UNIQUE`; a repeat returns the same refund (`shop_db.py:86-94`).
  Key format `<ticket_id>:<stage>` (`runner.py:46`).
- **Not picked.** Dedup in memory (lost on restart; test `tests/test_handled.py:10`). A distributed lock.
- **Mistakes.** Key in a different transaction from the effect; a key that is too coarse (blocks a legit second
  refund) or too fine (random UUID defeats the point); idempotency only in the consumer, not the tool.
- **Q1.** *Why is idempotency not an exactly-once claim?* Idempotent means repeats have no extra effect;
  exactly-once delivery is not claimed by this project. We build idempotent consumers.
- **Q2.** *Why is the key table in the same transaction?* Else a crash can save the key but lose the effect, or the
  reverse.

## 6. Retries with exponential backoff and jitter

- **eli5.** If a door is locked, wait 1 minute, then 2, then 4 before knocking. Add a small random wait so a
  whole crowd does not knock at the same second.
- **Why.** Transient errors (model down, network) often pass. Backoff protects the failing service. Jitter avoids
  a thundering herd.
- **Here.** `runner.py:54-67`; delay `runner.py:64`; injected `sleep` and `jitter` (`runner.py:27-28`).
  Test with exact delays `[2.2, 4.2]`: `tests/test_runner.py:51`.
- **Not picked.** A retry library (D-010): hides the lesson; the loop is about 15 lines.
- **Mistakes.** Retrying a poison message forever; no cap; no jitter; sleeping in tests.
- **Q1.** *Which errors to retry?* Transient ones. A `BadMessage` goes to the DLQ at once (`runner.py:60`).
- **Q2.** *Why inject the clock?* Tests assert exact delays and run in zero time.

## 7. Dead-letter queue (DLQ) and replay

- **eli5.** A "problem shelf". A letter we cannot handle goes there with a note saying why. A person fixes the
  cause and puts the letter back in line.
- **Why.** One bad message must not block the line, and must not vanish.
- **Here.** `_dead_letter` `runner.py:78` (headers `dlq-reason`, `dlq-source-topic`, `dlq-attempts`);
  `list_dead_letters` `runner.py:88`; `replay` `runner.py:101`; CLI `cli.py:27`. Test:
  `tests/test_runner.py:85` (3 cases: poison, schema, transient), `:127` (DLQ publish fails -> no commit), `:148`.
- **Not picked.** Dropping bad messages; infinite retry.
- **Mistakes.** Changing the body in the DLQ (we keep original bytes); no reason header; replaying without fixing
  the cause; no alert on DLQ growth (not built here).
- **Q1.** *Why commit after dead-lettering?* So the line moves on; the failed message is kept in the DLQ.
- **Q2.** *Is replay safe?* Only if consumers are idempotent.

## 8. Strict message contracts (Pydantic)

- **eli5.** A form with fixed boxes. Extra boxes or wrong types are rejected at the door.
- **Why.** Cheap validation at every trust boundary; clear error names.
- **Here.** `Payload` `extra="forbid", strict=True` (`messages.py:16`); discriminated union on `type`
  (`messages.py:105`); `parse_message` names bad fields (`messages.py:113`). Tests: `tests/test_messages.py:33`.
- **Not picked.** Avro plus registry (D-014): production step.
- **Mistakes.** Lenient coercion (`"true"` becomes `True`); extra fields silently ignored.
- **Q1.** *Why a discriminated union?* The `type` field picks the right model and gives precise errors.
- **Q2.** *Schema evolution?* Not solved here; a registry with compatibility rules would be the next step.

## 9. MCP servers with FastMCP

- **eli5.** A USB port for tools. Any agent that speaks the plug can use the shop's tools without custom code.
- **Why.** One standard way to expose tools to many agents and clients; the server owns the data rules.
- **Here.** `create_server` `mcp_server.py:13`; 4 `@server.tool` functions `:27-45`; errors become `ToolError`
  (`mcp_server.py:18-25`); client `mcp_client.py:26` (`raise_on_error=False`, then raises `McpError`).
  Tests: `tests/test_mcp_server.py:12`, `:40`; stdio child process: `tests/test_resolver.py:236`.
- **Not picked.** HTTP transport (needs a port); raw function tools inside the agent (not reusable, no process
  boundary).
- **Mistakes.** Letting exceptions leave the server; tool docstrings that do not tell the model valid ids;
  non-idempotent write tools.
- **Q1.** *Tool vs resource vs prompt in MCP?* Tool = action the model calls; resource = data to read; prompt =
  reusable template. We use tools only. (General MCP knowledge; UNVERIFIED here.)
- **Q2.** *Why stdio?* The client starts the server as a child process; no port, no auth to manage locally.

## 10. Triage agent with structured output

- **eli5.** Ask the model to fill a form, not write an essay. If the form is wrong, say "fix it" once. If still
  wrong, give up loudly.
- **Why.** Downstream code needs a fixed shape; models sometimes break JSON.
- **Here.** `Classification` `triage.py:17`; loop with one repair `triage.py:41-54`; error after the repair
  `triage.py:50`; scripted tests `tests/test_triage.py:52`, `:61`. The model sees the ticket as data
  (`triage.py:38`).
- **Not picked.** Provider JSON mode or tool-forced schema (works per provider; UNVERIFIED across the 4 providers
  here). Unlimited repair loops.
- **Mistakes.** Trusting the model's JSON; no cap on repairs; letting tool calls through when JSON was asked.
- **Q1.** *Why validate after the model?* Models are probabilistic; code is the gate.
- **Q2.** *What if triage is wrong?* The eval (F-009, coming next) measures it; the resolver still has its own
  checks.

## 11. LangGraph: state, nodes, edges

- **eli5.** A board game map. State is your game piece's bag. Each node is a square that changes the bag. Edges
  are arrows; conditional edges are "if X go left, else right".
- **Why.** Explicit control flow around LLM calls; each step is testable; the framework can save state between
  steps.
- **Here.** `ResolverState` `resolver.py:22`; six nodes `resolver.py:169`; edges `:172-178`;
  `route` conditional `:128`; step budget `:64`. Test: `tests/test_resolver.py:38`, `:56`, `:72`.
- **Not picked.** A hand-written state machine (Agent Lab already did it, `docs/ARCHITECTURE.md`); a free-running
  ReAct loop (less predictable, harder to cap money risk).
- **Mistakes.** Putting side effects before a checkpoint without an idempotency key; unbounded loops; model decides
  the amount without a code check.
- **Q1.** *Why a graph and not a loop?* Named steps, bounded paths, and a place to checkpoint.
- **Q2.** *Where does the LLM end and code begin here?* See `ARCHITECTURE.md`.

## 12. SQLite checkpointer, resume, interrupt

- **eli5.** Save-game. After every square, the game writes your bag to disk. If the power fails, load the save
  and carry on from the next square.
- **Why.** Long jobs and human waits must survive restarts, without redoing paid or risky steps.
- **Here.** `SqliteSaver(self.connection)` `resolver.py:193`; thread id = ticket id `resolver.py:201`;
  `get_state` decides start vs resume `resolver.py:203-206`. Test: `tests/test_resolver.py:87`
  (no repeated MCP reads). `interrupt` stub: `resolver.py:139`; test `:166`.
- **Not picked.** Postgres checkpointer (extra service, D-005); in-memory saver (lost on crash).
- **Mistakes.** Resuming with new input instead of `None`; non-idempotent nodes (a node may re-run after a crash
  mid-node); changing the graph shape with live checkpoints (UNVERIFIED behavior in LangGraph 1.2.18).
- **Q1.** *When is a checkpoint written?* After each node (LangGraph behavior; the test shows `next == ("decide",)`).
- **Q2.** *Checkpoint vs the handled store?* Handled = "did I finish this message?"; checkpoint = "where in the
  workflow am I?".

## 13. Test doubles that keep tests offline

- **Here.** `ScriptedModel` `fakes.py:14` (validates its script, records requests, raises `ScriptExhausted`);
  `MemoryBus`; injected `sleep` and `jitter`; the autouse socket guard `tests/conftest.py:19` blocks non-loopback
  and port 9092 connects in offline tests; kafka tests skip unless `AGENT_DESK_KAFKA_BOOTSTRAP` is set (`:11`).
- **Mistake.** A fake that is more forgiving than the real thing. `MemoryBus` copies redelivery and key order on
  purpose.
- **Q.** *How do you test "crash after the handler"?* Make `commit` raise (`tests/test_runner.py:22`).

## 14. Kafka offsets, manual commit, redelivery (F-010)

- **eli5.** Each team (group) has a bookmark in the roll of paper. The bookmark says "next line to read". If you
  move the bookmark BEFORE you finish the work and then crash, the line is lost. So move it AFTER the work.
  If you crash before moving it, the next reader starts at the same line: you see it twice, never zero times.
- **Why industry uses it.** This is how a consumer gets at-least-once delivery. The price is duplicates, so the
  handler must be idempotent.
- **Here.** `enable.auto.commit` is False `kafka_bus.py:79-81`. `poll` keeps one pending record
  `kafka_bus.py:98-116`. `commit` writes offset + 1 and waits for the broker `kafka_bus.py:118-125`. `close` does
  not commit `kafka_bus.py:127-130`. Offline proof with a fake client: `tests/test_kafka_bus_offline.py:58`
  (log order: handled, then commit). Live proof: `tests/kafka/test_kafka_live.py:43` (no commit, new consumer
  in the same group gets the record again).
- **Not picked.** Auto commit (commits on a timer, can commit work that never finished); async commit (the
  program could go on before the broker has saved the bookmark); Kafka transactions (exactly-once is not claimed;
  they do not cover the database write).
- **Mistakes.** Committing `offset` instead of `offset + 1` (the same record comes back forever); committing
  before the handler; reading ahead while a record is pending, then committing a later offset (skips the failed
  record).
- **Q1.** *When do you commit and why?* After the handler returns. A crash then gives a duplicate, not a loss.
- **Q2.** *What does a consumer group rebalance do to uncommitted work?* The partition moves to another member,
  which starts at the last committed offset, so uncommitted records are delivered again.
- **Q3.** *Why is Kafka on Windows only for development?* Apache does not officially support it; file-locking
  errors on log deletion are known (DOCUMENTED, README caveat). High retention avoids deletion.
