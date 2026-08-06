# FinSentinel AI

**Cloud-native, multi-agent banking risk, fraud, AML, and credit intelligence platform.**

This repository is the Day-1 foundation for a 10-day production-style portfolio build. It already contains:

- FastAPI backend with health, transaction scoring, and investigation endpoints
- Deterministic multi-agent orchestration skeleton
- Next.js dashboard shell
- PostgreSQL, Redis, Qdrant, Neo4j, Redpanda, MinIO, Keycloak
- Prometheus, Grafana, and Jaeger service definitions
- GitHub Actions CI
- Kubernetes baseline manifests
- Synthetic banking transaction generator

## Architecture

```text
Next.js Dashboard
        |
        v
FastAPI API + Agent Orchestrator
        |
        +-- PostgreSQL  (banking records, cases, audit)
        +-- Redis       (cache, short-term state)
        +-- Qdrant      (policy and semantic evidence)
        +-- Neo4j       (entity and transaction graph)
        +-- Redpanda    (Kafka-compatible event stream)
        +-- MinIO       (documents and model artifacts)
        +-- Keycloak    (OAuth/OIDC and RBAC)
        +-- OTel -> Jaeger / Prometheus / Grafana
```

## Local quick start

### Requirements

- VS Code
- Docker Desktop with Docker Compose
- Git
- Node.js 20+
- Python 3.11+

### Run the complete local stack

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web dashboard: http://localhost:3000
- FastAPI docs: http://localhost:8000/docs
- Grafana: http://localhost:3001
- Prometheus: http://localhost:9090
- Jaeger: http://localhost:16686
- Neo4j Browser: http://localhost:7474
- Qdrant dashboard: http://localhost:6333/dashboard
- MinIO console: http://localhost:9001
- Keycloak: http://localhost:8080

### Run only the API locally

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

### Generate synthetic banking transactions

```bash
python scripts/generate_synthetic_data.py --count 500 --output data/generated/transactions.jsonl
```

## Implemented endpoints

- `GET /health/live`
- `GET /health/ready`
- `GET /metrics`
- `POST /api/v1/transactions/score`
- `POST /api/v1/investigations/run`

The investigation endpoint demonstrates the typed orchestration contract. It runs fraud, behavior, graph, and policy agents, aggregates evidence, applies a critic, and returns a human-review decision when risk is high.

## Ten-day delivery map

See [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md).
