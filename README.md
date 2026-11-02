# Agent Desk

An event-driven support desk for a fictional shop. Triage classifies tickets;
LangGraph resolves them through MCP shop tools. Large refunds pause for a person.
The offline implementation uses `MemoryBus` and scripted model replies. Kafka is
planned for F-010. See `docs/PRODUCT_SPEC.md` and `feature_list.json` for the spec.

## Run offline

From the project folder, with the existing Python 3.12 environment:

```powershell
.venv\Scripts\python.exe -m agent_desk.cli --help
.venv\Scripts\python.exe -m agent_desk.cli run --fake --count 2
.venv\Scripts\python.exe -m agent_desk.cli eval triage --fake
.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp-offline
```

On a fresh local state, the demo prints `Handled triage=2, resolver=2, decisions=0`
and a result table. Eval prints category and priority accuracy `1.0000`, a confusion
table, and writes `runs/eval-<time>.json`. The fake copies labels to check the eval
plumbing; this score does not measure a real model. JSON event logs and local trace
exports go to stderr. No OTLP exporter is enabled.

The demo seeds the shop and uses the configured checkpoint path plus
`.agent-desk/handled.sqlite`. Saved keys make later runs skip tickets already done.
Use separate `AGENT_DESK_DB_PATH`, `AGENT_DESK_CHECKPOINT_PATH` and `--handled-path`
values for an independent demo. Do not delete a working desk's state to reset a demo.
No package install or dependency change is needed for these commands.

## Follow the logic

1. `src/agent_desk/simulator.py:38` reads 40 labeled fictional tickets, shuffles with
   a seed, and publishes tickets without labels. `simulate --count 5 --seed 7
   --poison 2 --duplicate 2` publishes nine messages: five tickets, two exact repeats
   and two malformed messages.
2. `src/agent_desk/triage.py:33` checks the model's category and priority and publishes
   work. The runner saves the handled key after the handler returns.
3. `src/agent_desk/resolver.py:141` pauses large refunds with LangGraph `interrupt`.
   The work handler publishes an approval request and returns, so other tickets flow.
4. `src/agent_desk/approver.py:42` publishes the reviewer, note and decision. The
   resolver decision runner resumes the saved graph, then refunds or replies with
   the rejection note. The stable refund key prevents a second payment.
5. `src/agent_desk/telemetry.py:50` extracts trace context from headers. Each outgoing
   message carries the active span context. A restart can follow the same trace.
6. `src/agent_desk/evals.py:22` measures category and priority accuracy and confusion
   cells. `results` prints the final status, refund and reply in a table.

Delivery is at-least-once; exactly-once is not claimed. Publishing and saving a
handled key are separate steps, so a crash can publish twice. Consumers use stable
ticket and stage keys. `tests/test_approval.py` proves that a crash after triage's
publish produces two work messages but one refund and one result.

## CLI and web approvals

`approve` lists pending requests. `approve T-100 --accept --reviewer Sam --note
"Checked order"` publishes approval; use `--reject` to decline. `approve --web`
serves the same actions at `http://127.0.0.1:8765`. The server binds to IPv4 loopback
only. Its form token rejects submissions that did not come from the local page.

MemoryBus lives in one process. Separate terminal invocations of `simulate`,
`approve` and `results` do not share messages. The standalone `run --fake` command
creates tickets and drains both agents in one process. For a shared offline session,
call `agent_desk.cli.main([...], bus=bus)` with the same `MemoryBus`; tests show the
full sequence. `run triage` and `run resolver` drain their selected stage, and
`run resolver` also consumes decisions. Cross-process topic persistence comes in F-010.
The pending page reconstructs its view from requests and decisions, collapsing
repeated requests and hiding tickets that have a decision.

## Learn and check

Read `lessons/05-approvals.md`, `lessons/observability.md` and
`lessons/simulation-and-eval.md` for commands, expected output and code references.
The existing `docs/learn/` pack is preserved as the F-001 through F-006 learning snapshot.
Tests use scripted models, a memory bus and temporary SQLite files. They need no
broker or model server. Kafka and live tests remain opt-in. If `uv` runs on your
host, `uv run pytest` is the equivalent offline test command. Ruff is not configured.

Quiz: What happens if triage crashes after publishing work? Why can a human pause
survive a resolver restart? What does a perfect score from the copying fake prove?
