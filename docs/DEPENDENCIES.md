# Agent Desk: dependencies

Exact direct versions read from the existing `uv.lock` on 2026-11-02.
The environment was supplied already installed. No packages were installed or changed.
Hashes and transitive versions remain in `uv.lock`. Licences and upstream releases were not checked (offline).

| Package | Version | Use |
|---|---|---|
| langgraph | 1.2.18 | runtime |
| langgraph-checkpoint-sqlite | 3.1.3 | runtime |
| litellm | 1.106.6 | runtime |
| langchain-litellm | 0.11.2 | runtime |
| fastmcp | 4.1.4 | runtime |
| pydantic | 2.14.2 | runtime |
| opentelemetry-api | 1.45.2 | runtime |
| opentelemetry-sdk | 1.45.2 | runtime |
| confluent-kafka | 2.16.1 | runtime |
| tzdata | 2026.6 | runtime |
| pytest | 9.2.0 | dev |
| pytest-xdist | 3.8.0 | dev |

The build backend is hatchling, declared without a version in the existing pyproject.toml.
It is not a runtime dependency and has no entry in the supplied uv.lock.

Host tools (not Python packages; set up by the human, F-010):

| Tool | Version | Source | Check |
|---|---|---|---|
| Eclipse Temurin JDK | 21.0.13+9 | winget `EclipseAdoptium.Temurin.21.JDK`, installed by the human 2026-11-02 | `C:\Program Files\Eclipse Adoptium\jdk-21.0.13.9-hotspot` |
| Apache Kafka | 4.3.2 (`kafka_2.13-4.3.2.tgz`, 135,281,924 bytes) | https://downloads.apache.org/kafka/4.3.2/ | SHA-512 verified against the published `.sha512` (2026-11-02); unpacked to `.kafka/` (git-ignored) |

No Docker or cloud resources are used.
