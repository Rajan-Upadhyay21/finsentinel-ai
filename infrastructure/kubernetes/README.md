# FinSentinel Kubernetes Operations

## Local deployment

```bash
helm upgrade --install finsentinel \
  infrastructure/helm/finsentinel \
  --namespace finsentinel \
  --create-namespace \
  --atomic
```

## Status

```bash
kubectl get pods -n finsentinel
kubectl get deployments -n finsentinel
helm history finsentinel -n finsentinel
```

## Rollback

```bash
helm rollback finsentinel <REVISION> \
  -n finsentinel \
  --wait
```

## Reliability controls

FinSentinel uses startup/readiness/liveness probes, rolling updates,
graceful pre-stop handling, resource requests/limits, HPA configuration,
PDB configuration, NetworkPolicy configuration, Kubernetes self-healing,
and Helm atomic deployment rollback.

Production secrets are supplied through an existing Kubernetes Secret
and are not stored in Git.
