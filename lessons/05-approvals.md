# Human approval: save, pause, resume

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
