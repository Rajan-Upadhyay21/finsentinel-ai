# FinSentinel AI — Recruiter Demo

## Goal

Demonstrate an end-to-end suspicious-transaction investigation in approximately 5–7 minutes.

The demo should show that FinSentinel is not only an ML model. It connects banking data, risk scoring, multi-agent evidence, security, human review, observability, and Kubernetes operations.

## Scenario

Use the seeded suspicious transaction `TXN-9001`.

Its synthetic context includes elevated device, IP, merchant, anomaly, and fraud signals, making it suitable for a high-risk investigation path.

## Demo Story

### 1. Start with the platform

Show the dashboard and explain:

> FinSentinel is a cloud-native banking intelligence platform. A transaction can be scored by ML, investigated by specialized agents, grounded with graph and policy evidence, routed to a human reviewer, and monitored through production telemetry.

### 2. Show the banking record

Highlight the transaction identifier, amount/type/status, device-known signal, IP risk, merchant risk, fraud probability, and anomaly score.

### 3. Run the investigation

Trigger the fraud investigation endpoint or dashboard action.

Explain the execution path:
1. API validates request and identity.
2. Specialized capabilities execute through the orchestrator.
3. Agent execution has timeouts and failure isolation.
4. Evidence is aggregated.
5. Combined risk is classified.
6. Critical cases require human review.

### 4. Explain the AI design

- XGBoost → supervised fraud signal
- Isolation Forest → anomalous-behavior signal
- Neo4j → relationship evidence
- Qdrant → semantic policy/evidence retrieval
- multi-agent orchestrator → workflow coordination
- human-review layer → governed decision path

### 5. Show observability

Open Prometheus/Grafana/Jaeger where available and point out workflow count/duration, agent latency, timeouts/failures, human-review decisions, risk-level distribution, model-score distributions, drift indicators, and traces.

### 6. Show Kubernetes

```bash
kubectl get deployments,pods,services -n finsentinel
helm list -n finsentinel
```

For resilience:

```bash
kubectl delete pod   $(kubectl get pods -n finsentinel     -l app.kubernetes.io/component=api     -o jsonpath='{.items[0].metadata.name}')   -n finsentinel
```

Then show the replacement pod becoming ready.

### 7. Close with architecture

End on the README architecture diagram and explain that the engineering goal was to connect model intelligence to authenticated APIs, persisted cases, multi-agent evidence, graph/vector retrieval, human review, auditability, observability, drift monitoring, CI/CD, Helm, and Kubernetes.

## Interview Talking Points

### Why multi-agent instead of one LLM call?
Different banking investigations require different evidence sources, tools, timeouts, permissions, and failure handling. Specialized agents make those boundaries explicit and independently observable.

### Why XGBoost plus Isolation Forest?
The supervised model captures learned fraud patterns while the unsupervised model adds a signal for behavior that differs from the reference distribution.

### Why Qdrant and Neo4j?
Qdrant handles semantic similarity over textual evidence; Neo4j handles relationship-oriented evidence.

### How do you prevent agent failures from crashing the investigation?
Agent calls have bounded execution time and failure isolation. The orchestrator can retain warnings/evidence and continue when policy allows.

### How is this governed?
Protected workflows use server-side authorization. High-risk results can require human review, and investigation actions are represented in the audit trail.

### How do you monitor model quality without immediate labels?
FinSentinel monitors label-free feature and prediction-distribution drift as an early signal. True performance evaluation requires delayed ground-truth labels.

### What would you change for a real bank?
Use managed infrastructure, enterprise secrets/KMS, private networking, formal model-registry approvals, delayed-label monitoring, SIEM/data-lineage controls, compliance mapping, disaster recovery, and production GitOps environments.

## Screenshot Checklist

Capture:
1. dashboard landing/overview
2. suspicious transaction
3. investigation result with risk level/human review
4. Grafana metrics
5. Jaeger trace
6. Kubernetes pods/services
7. Helm release
8. GitHub README architecture

Use synthetic data only. Do not include secrets, tokens, `.env` contents, or personal credentials.

## Demo Success Criteria

A complete demo proves the banking transaction exists, ML risk scoring works, the investigation workflow executes, specialized agent evidence is returned, human review can be triggered, authorization is enforced, operational metrics/traces exist, Kubernetes workloads are healthy, Helm is deployed, and repository documentation clearly explains the system.
