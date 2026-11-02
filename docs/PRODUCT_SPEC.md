# Agent Desk: product spec

Status: draft for the SPEC GATE (2026-11-02). Source: `plan/idea.md`.

## Vision
A small codebase that teaches event-driven agent systems. A fictional shop gets support tickets. Each ticket is an
event on Kafka. Agents read events, do work and write new events. Risky actions wait for a human. The learner reads
and runs each part, and sees what happens when things fail.

Skills shown: Kafka, advanced LangGraph (durable state, interrupts), MCP, human-in-the-loop, reliability
(idempotency, retries, dead letters), tracing. The domain is a shop support desk. It is not hiring, assessment or
edtech.

## User
One learner (the owner) on a Windows PC (no Docker; Kafka runs natively). Knows Python. New to Kafka, advanced LangGraph and
reliability patterns. Also a reader (a hiring manager or peer) who skims the README and the diagram.

## Scope (in)
- Kafka as a native Windows binary, KRaft mode, one broker.
- Topics: incoming tickets, agent work, approval requests, approval decisions, results, dead letters.
- A ticket simulator (producer) with seeded, labeled tickets.
- Triage agent (Kafka consumer): classify the ticket and set priority.
- Resolver agent (Kafka consumer): a LangGraph graph with a checkpointer. It calls MCP tools from a FastMCP "shop"
  server (order lookup, refund policy, shipment status) over a seeded SQLite DB.
- Human approval for refunds above a limit: a request topic, a CLI approver and a minimal web approver.
- Idempotency keys, retries with backoff, dead-letter handling.
- Structured logs and OpenTelemetry traces across Kafka hops (trace context in message headers).
- LLM calls through LiteLLM: local Qwen on llama-server, or free Gemini, Groq or NVIDIA NIM.
- Evals: triage accuracy on a labeled ticket set.
- Lessons 01-06 and, later, an interactive architecture diagram.

## Scope (out)
- Exactly-once delivery is not claimed. The project explains at-least-once plus idempotent consumers instead.
- Real payments, real customers, real email.
- Multi-broker clusters, schema registry, Kafka Streams.
- Auth, multi-tenant, production hosting.

## Success
1. `uv run pytest` passes with no Kafka, no model and no network.
2. With the broker up, the simulator sends tickets and the full flow runs: triage, resolve, approve, result.
3. A refund above the limit stops at the approval step. The graph state survives a process restart.
4. A poison message lands on the dead-letter topic after the retry limit. A duplicate message causes no second effect.
5. One trace spans producer, triage, resolver and approver.
6. The triage eval prints accuracy and a confusion table for the labeled set.
7. Every source file has plain-English comments (eli5, ASD-STE100 style).

## Journeys
- **Learn one idea.** Read `lessons/0N_*.md`, run its script, read the commented source.
- **Run the desk.** start Kafka with `scripts/kafka-local.ps1`, start the agents, run the simulator, approve a refund in the CLI.
- **Break it.** Kill the resolver mid-ticket, restart it, and watch it resume from the checkpoint. Send a poison
  ticket and find it on the dead-letter topic.
- **Test without Kafka.** `uv run pytest` uses the in-memory bus and the scripted model.
- **Measure triage.** `uv run agent-desk eval triage` prints accuracy for the chosen model.
