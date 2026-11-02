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

Java 21 Temurin JDK and the Apache Kafka binary distribution are deferred to F-010.
Their host installation and exact versions are unverified. No Docker or cloud resources are used.
