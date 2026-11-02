# Start here: Agent Desk learning pack

## What this project is (eli5)

Think of a post office. Customers drop letters (support tickets) in a box. Workers take one letter at a time.
One worker sorts the letter ("this is a refund, it is urgent"). The next worker reads the order, decides, and
writes back. If a letter is torn, it goes to a "problem" shelf, and a person can look at it and put it back in line.

Agent Desk is that post office, in Python. The box is a **message bus** (topics). The workers are **consumers**.
Two workers use an LLM: a **triage agent** and a **resolver graph**. The shop data sits behind an **MCP server**.
The aim of the project is to learn how real agent systems survive crashes, repeats and bad input.

## What you will learn

- Event-driven design: events, topics, keys, consumer groups, why Kafka.
- At-least-once delivery and idempotent consumers.
- Retries with exponential backoff and jitter, dead-letter queue (DLQ), replay.
- MCP servers with FastMCP (tools, error results, idempotent tools).
- A triage agent with structured output (Pydantic) and one repair prompt.
- LangGraph: state, nodes, edges, conditional edges, SQLite checkpointer, resume after a crash.

## Prerequisites

- Python basics (functions, classes, dicts, exceptions). SQL basics (SELECT, INSERT, transaction).
- No Kafka, no model server and no network needed. The offline tests use `MemoryBus` and `ScriptedModel`.

## Run it offline in 3 commands

From `D:\Projects\agent-desk` in PowerShell:

```powershell
.venv\Scripts\python.exe -m pytest -q -m "not live"          # all offline tests
.venv\Scripts\python.exe -m pytest -q tests/test_runner.py   # the retry / DLQ / idempotency tests
.venv\Scripts\python.exe -m agent_desk.cli --help            # the command list
```

MEASURED on this PC (2026-11-02): the first command gives `79 passed` in about 32 s.

## What is built and what is "coming next"

Only features with status `passing` in `feature_list.json` are taught in depth.

| Feature | Status | In this pack |
|---|---|---|
| F-001 Project setup, settings, markers | passing | settings.py, test markers (TOPICS.md) |
| F-002 Messages, Bus interface, MemoryBus | passing | lesson 1 |
| F-003 Runner: idempotency, retries, DLQ, replay | passing | lessons 2 and 3 |
| F-004 Seeded shop DB, FastMCP server | passing | lesson 4 |
| F-005 LLM client, ScriptedModel, triage agent | passing | lesson 5 |
| F-006 Resolver LangGraph graph, SQLite checkpointer | passing | lesson 6 |
| F-007 Human approval: interrupt, decisions topic, approver | coming next | only a stub exists (see lesson 6) |
| F-008 Structured logs, OpenTelemetry traces | coming next | not covered |
| F-009 Simulator, CLI wiring, triage eval | coming next | not covered |
| F-010 Native Kafka on Windows, KafkaBus | coming next | shown as "planned" in the diagram |
| F-011 Lessons 01-06 in the project | coming next | this pack is the deeper layer; lesson names here start with `deep-` |

## Learning path

| Order | Read | Time |
|---|---|---|
| 1 | this file, then `ARCHITECTURE.md` and open `architecture.html` in a browser | 30 min |
| 2 | `lessons/deep-01-event-bus.md` | 40 min |
| 3 | `lessons/deep-02-delivery-and-idempotency.md` | 45 min |
| 4 | `lessons/deep-03-retries-dlq-replay.md` | 45 min |
| 5 | `lessons/deep-04-mcp-fastmcp.md` | 40 min |
| 6 | `lessons/deep-05-triage-structured-output.md` | 40 min |
| 7 | `lessons/deep-06-langgraph-checkpoint-resume.md` | 60 min |
| 8 | `TOPICS.md` (reference), `GLOSSARY.md` | 30 min |
| 9 | `INTERVIEW.md`, say the story out loud | 30 min |

Rule used in this pack: a claim is MEASURED (a test or command ran here), or DOCUMENTED (URL and date), or
UNVERIFIED. Statements about Kafka behavior are general knowledge and marked UNVERIFIED for this project until F-010.
