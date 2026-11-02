# AGENTS.md: map of agent-desk

Learning project: an event-driven support desk for a fictional online shop. Tickets flow through Kafka. Agents are
consumers: a triage agent and a resolver agent (LangGraph, durable state, MCP shop tools). A human approves big
refunds. Built through the crosscheck harness (Claude orchestrates, Codex implements).

## Rules
1. No secrets in files. LLM keys come only from env vars: GEMINI_API_KEY, GROQ_API_KEY, NVIDIA_NIM_API_KEY.
   Never read `.env`, token files or `~/.ssh`. Free tiers only. No paid services.
2. Offline tests never need Kafka, a model or network. Use the in-memory bus fake and the scripted model fake.
   Kafka tests are marked `@pytest.mark.kafka` and are opt-in: they run only when `AGENT_DESK_KAFKA_BOOTSTRAP`
   (the bootstrap address, for example `127.0.0.1:9092`) is set. Live model tests are marked `@pytest.mark.live`.
3. Only touch files listed in the task spec. Never weaken tests. Status in feature_list.json changes only via the
   harness `verify_feature.py`.
4. Exact dependency pins; log every dependency in docs/DEPENDENCIES.md. No installs without human approval.
5. Plain-English comments (eli5 level, ASD-STE100 style) on every module and public function.
6. Delivery is at-least-once. Every consumer is idempotent. Never claim exactly-once.
7. No Docker (not available on this PC, D-017). Kafka runs natively on Windows for development (Java 21 Temurin JDK +
   Apache Kafka binary distribution, KRaft mode, started by a PowerShell script). Kafka does not officially support
   Windows for production. Fallback: a remote EC2 Kafka (UNVERIFIED); agents never create cloud resources.
8. Never push, publish or deploy without explicit human approval.
9. Native Windows host; pathlib; UTF-8, LF. Python 3.12 via uv.

## Map
| Path | What |
|---|---|
| progress.md | Current state, next step |
| docs/PRODUCT_SPEC.md | Vision, scope, journeys |
| docs/REQUIREMENTS.md | REQ-### with acceptance criteria |
| docs/ARCHITECTURE.md | Stack, layout, topics, contracts |
| docs/DECISIONS.md | Decisions and assumptions |
| docs/DEPENDENCIES.md | Planned and installed packages |
| docs/exec-plans/ | Phase plans |
| feature_list.json | Features F-001..F-011 |
| plan/ | Intake artifacts (idea.md, plan.json) |
| lessons/ | Step-by-step lessons 01-06 |
| src/agent_desk/ | The code |
| tests/ | Offline tests; `tests/kafka/` is opt-in |

## Commands
- Tests (offline): `uv run pytest`
- Kafka tests (broker up, env var set): `$env:AGENT_DESK_KAFKA_BOOTSTRAP="127.0.0.1:9092"; uv run pytest -m kafka -n 0`
- Broker: `powershell -File scripts/kafka-local.ps1 start` and `... stop` (script written at F-010)
- Run the desk: `uv run agent-desk --help`
