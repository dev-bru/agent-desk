# Phase 2: Kafka, observability, evals, lessons (F-008..F-011)

Status: planned (2026-11-02). Starts after phase 1 is green.

## Features (in order)
8. F-008 structured logs and OpenTelemetry traces across hops (on MemoryBus)
9. F-009 ticket simulator, CLI wiring, triage eval
10. F-010 Native Kafka on Windows (KRaft, PowerShell script), KafkaBus, topics, opt-in Kafka tests
11. F-011 lessons 01-06, README, comment check, then the interactive diagram (REQ-062)

## Done when
- With the local broker up (`scripts/kafka-local.ps1 start`), `agent-desk simulate` then the agents then `agent-desk approve` runs the full flow.
- One trace covers all hops. The triage eval prints accuracy.
- Lessons 01-06 run offline with `--fake`.
- `uv run pytest` green offline; `uv run pytest -m kafka -n 0` green with the broker up and `AGENT_DESK_KAFKA_BOOTSTRAP` set.

## Notes
- F-010 is the first feature that needs a broker (no Docker, D-017). Before the spec, ask the human to approve the Java 21
  Temurin JDK and Kafka binary installs; check the Kafka client wheel on Windows and the broker memory use
  (see Risks in ARCHITECTURE.md). Measure and record in DECISIONS.md (D-002).
- Kafka on Windows is for development only; set retention high and expect possible log-deletion file-lock errors on
  long runs. Fallback: a remote EC2 Kafka (UNVERIFIED, created by the human, never by an agent).
- Never leave the broker running when idle: `scripts/kafka-local.ps1 stop`.
- The diagram is built with the architecture-diagram skill after the flows are real.
