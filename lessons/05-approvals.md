# 05: Human approval: save, pause, resume

Concept: a human decision is a separate event that resumes saved graph state.

A large refund must wait for a person. Holding the consumer open would stop other
tickets. Instead, LangGraph saves the ticket and returns an interrupt. The work
handler publishes a request and returns. A separate decision runner resumes the
same checkpoint with `Command(resume=...)`.

Read `src/agent_desk/resolver.py:141` for the pause and
`src/agent_desk/approver.py:42` for the human decision producer.
The refund tool still uses the stable ticket refund key, so retries cannot pay twice.
Reject goes to reply without calling the refund tool and keeps the reviewer's note.

Run from the project folder:

```powershell
.venv/Scripts/python.exe -B lessons/05-approvals.py --fake
```

Expected output on stdout (logs and trace spans also go to stderr):

```text
Pending: T-1 refund 75.00 above limit 50.00; no result yet
Approved after restart: refunded 75.00; 1 refund; 1 result despite duplicate decision
```

Follow the logic step by step:

1. The script puts a refund ticket for order `O-2`, owned by `C-2`, on `desk.work`.
   It uses `MemoryBus`, fixed model replies, and real in-process MCP shop tools.
2. The model proposes 75.00. Code checks the order total and the automatic limit
   of 50.00. The graph saves state and pauses before the refund tool runs.
   The handler publishes `approval.requested` and returns to the consumer.
3. Close the resolver and its handled store. Build both again from the same files.
   The empty model script on the new resolver proves that resume needs no new
   model answer. The script calls the same decision producer a reviewer uses.
4. The decision runner uses a separate `T-1:decision` key. The approved graph
   resumes, issues the refund, and publishes its result. A repeated decision is
   skipped. The script checks one refund row, one result, and no pending request.

Files to read: `src/agent_desk/resolver.py:141` (pause),
`src/agent_desk/resolver.py:245` (decision handler),
`src/agent_desk/approver.py:42` (decision producer), and
`src/agent_desk/shop_db.py:74` (refund key).
For the longer state explanation, read
[deep lesson 6](../docs/learn/lessons/deep-06-langgraph-checkpoint-resume.md).
That learning pack is an F-001 through F-006 snapshot; its approval stub has since
been replaced by the F-007 implementation taught here.

The script creates and removes its own `.pytest-tmp-lesson05-*` folder in the
project. SQLite keeps graph state and handled keys across the resolver rebuild;
the same MemoryBus instance stays alive throughout. Sharing topics between
separate processes via native Kafka is coming with F-010.

Check the approval and rejection paths, including other tickets while one waits:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_approval.py tests/test_approver.py --basetemp=.pytest-tmp-approvals
```

Expected output: `6 passed`. The tests use the real graph and in-process MCP shop,
with scripted model replies and a memory bus. The HTTP test uses loopback only.

The publish and handled-key write are separate steps. A crash can publish twice.
The downstream runner absorbs this with the ticket's stable stage key. This is
at-least-once delivery; exactly-once is not claimed. Approval requests also use a
stable message id, and the pending view collapses duplicates by ticket.

Quiz: Why does a decision need its own handled key? Why must the refund tool also
keep a key? Which saved state lets a new resolver process resume without a model call?
