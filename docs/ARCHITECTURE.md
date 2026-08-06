# Architecture decisions

## Modular monolith first

The ten-day implementation uses a modular FastAPI application rather than many independently deployed microservices. Domain boundaries remain explicit so components can later be extracted without rewriting the business logic.

## Hybrid decision intelligence

LLMs are used for planning, evidence synthesis, and explanation. Deterministic rules, ML models, SQL analytics, and graph queries remain authoritative for calculations and policy enforcement.

## Evidence-gated decisions

A final decision requires structured evidence, contradiction checks, confidence thresholds, and human approval for high-risk outcomes.

## Storage responsibilities

- PostgreSQL: authoritative transactional records
- Redis: cache, locks, short-term workflow state
- Qdrant: semantic policy and document retrieval
- Neo4j: entity relationships and transaction networks
- MinIO: raw documents and model artifacts
- Redpanda: Kafka-compatible event transport
