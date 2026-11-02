# Agent Desk: dependencies

Planned only. Nothing is installed. Every version is "pin at setup": at F-001 the orchestrator checks PyPI (or the
download page), picks an exact version, records the source and date here, and asks the human to approve before
install. Exact hashes live in `uv.lock`. Labels: MEASURED, DOCUMENTED (URL + date), UNVERIFIED.

## Python packages (direct, planned)
| Package | Version | Licence | Why | Source |
|---|---|---|---|---|
| langgraph | pin at setup | check at setup | Resolver graph | UNVERIFIED |
| langgraph-checkpoint-sqlite | pin at setup | check at setup | SQLite checkpointer | UNVERIFIED |
| litellm | pin at setup | check at setup | One API for every model provider | UNVERIFIED |
| langchain-litellm | pin at setup (only if the graph needs a chat model object) | check at setup | `ChatLiteLLM` for LangGraph | UNVERIFIED |
| fastmcp | pin at setup | check at setup | Shop MCP server and client | UNVERIFIED |
| confluent-kafka | pin at setup (F-010) | check at setup | Kafka client | UNVERIFIED |
| pydantic | pin at setup | check at setup | Message models | UNVERIFIED |
| opentelemetry-api | pin at setup | check at setup | Trace API | UNVERIFIED |
| opentelemetry-sdk | pin at setup | check at setup | Spans and exporters | UNVERIFIED |
| tzdata | pin at setup | check at setup | Time zones on Windows | UNVERIFIED |
| pytest (dev) | pin at setup | check at setup | Tests | UNVERIFIED |
| pytest-xdist (dev) | pin at setup (optional) | check at setup | Parallel offline tests | UNVERIFIED |

## Runtime tools (host, installed by the human at F-010; no Docker, D-017)
| Tool | Version | Why | Source |
|---|---|---|---|
| Java 21 Temurin JDK | pin at F-010 | Runs the Kafka broker | UNVERIFIED |
| Apache Kafka binary distribution (KRaft mode) | pin at F-010 | Development broker on Windows; not supported for production | UNVERIFIED |
| Remote Kafka on AWS EC2 (optional fallback) | not installed | Documented fallback; no resource created by agents | UNVERIFIED |

## Not used
- Redpanda: see D-002.
- A retry library: see D-010.
- Flask or FastAPI: see D-012.

## Supply chain
Exact `==` pins, hashes in `uv.lock`. Review each package and its transitive packages before install. LiteLLM had
bad releases in 2026 (UNVERIFIED detail): check the release notes before pinning. Resolve conflicts (for example
`mcp` version ranges between fastmcp and LangChain packages) at setup and record the result here.
