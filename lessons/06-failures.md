# 06: Failures, retries, dead letters, and replay

Concept: delivery is at-least-once. A consumer commits after work succeeds or after
it safely publishes a dead letter. A crash before commit can cause redelivery.
Consumers must use stable keys to make repeats safe; exactly-once is not claimed.

Run from the project folder:

```powershell
.venv/Scripts/python.exe -B lessons/06-failures.py --fake
```

Expected output on stdout (logs and trace spans also go to stderr):

```text
Dead letters: poison attempts=0; T-1 attempts=3; retry delays=[1.0, 2.0]
Next delivery succeeded after repair; replay skipped its handled key; 1 saved effect
Delivery is at-least-once; exactly-once is not claimed
```

Follow the logic step by step:

1. Publish malformed bytes, a valid `T-1` event, and a repeat of `T-1` on
   `MemoryBus`. Bad JSON fails before the handler and goes straight to
   `desk.dead-letter` with `dlq-attempts=0`. It does not block the valid record.
2. The handler writes a row, then fails for its first three calls. `Handled.run()`
   rolls back both the row and handled key on each failure. The runner waits
   `base * 2 ** (attempt - 1)` plus jitter between attempts, up to three attempts.
   This script records waits and sets jitter to zero: `[1.0, 2.0]`, with no sleeping.
3. After three failures, the runner publishes the original bytes to the dead-letter
   topic with reason, source topic, and attempt headers, then commits the input.
   The simulated service recovers after its third call. The next delivery of
   `T-1` succeeds and saves one row plus its handled key.
4. Replay republishes the failed record to its source topic, stripping retry and
   DLQ headers. Because another delivery already completed `T-1:triage`, the
   runner skips the replay. The row count stays one. If the ticket had not finished,
   replay would call its handler again. Replaying poison bytes without fixing the
   producer or schema would only dead-letter them again.

Files to read: `src/agent_desk/runner.py:47` (parse and handled key),
`src/agent_desk/runner.py:64` (retry loop), `src/agent_desk/runner.py:85`
(dead-letter headers), `src/agent_desk/runner.py:108` (replay), and
`src/agent_desk/handled.py:21` (atomic local writes).
Read [deep lesson 2](../docs/learn/lessons/deep-02-delivery-and-idempotency.md)
and [deep lesson 3](../docs/learn/lessons/deep-03-retries-dlq-replay.md) for more detail.

Publishing to a bus and saving a handled key are separate operations. A crash can
publish twice, so downstream consumers also need stable stage keys. A shop refund
is outside the handled database transaction and has its own refund key. A fixed
message id alone does not stop duplicate effects.

Today's executable path uses MemoryBus, a temporary in-memory handled store, and
an injected clock; no broker, model server, or network is needed. Kafka restart,
offset, and broker failure exercises are coming with F-010. MemoryBus topic data
itself is lost when the process exits.

Quiz: Why must commit come last? Why does failed work leave no row? Why is replay
skipped here? Can a SQLite transaction also roll back a published bus message?
