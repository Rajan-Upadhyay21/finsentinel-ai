# FinSentinel GitOps Delivery

The Argo CD Application tracks `main` and renders the production
FinSentinel Helm values.

Production secrets are intentionally not committed.

Create the required secret before enabling the production application:

```bash
kubectl create secret generic finsentinel-api-secrets \
  --namespace finsentinel \
  --from-env-file=.env.production
```

The application uses automated synchronization, self-healing, pruning,
namespace creation, and production Helm values.
