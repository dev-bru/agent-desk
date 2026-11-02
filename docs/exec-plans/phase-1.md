# Phase 1: Offline core (F-001..F-007)

Status: planned (2026-11-02). One feature at a time through /delegate. Spec per feature from the harness template.
Evaluator review. `verify_feature.py` sets status. No Kafka, no model, no network in this phase.

## Features (in order)
1. F-001 project setup, settings, markers, dependency record
2. F-002 message schemas, Bus interface, MemoryBus
3. F-003 runner: idempotency, retries, backoff, dead letter, replay
4. F-004 shop DB and FastMCP shop server
5. F-005 LLM client, ScriptedModel, triage agent
6. F-006 resolver LangGraph graph with checkpointer
7. F-007 human approval flow and approver (CLI + web)

## Done when
A ticket on `MemoryBus` goes through triage and resolver with scripted models. A big refund waits for approval and
resumes after a restart. A poison message reaches the dead-letter topic. `uv run pytest` is green and needs nothing
external. Full `uv run pytest` green after every feature.

## Notes
- Install the pinned packages only after the human approves the dependency list (rule 4).
- Keep each feature to about 5 files. Split the spec if it grows.
