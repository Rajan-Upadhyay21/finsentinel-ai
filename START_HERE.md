# Start Here — macOS + VS Code

## 1. Open the project

```bash
unzip finsentinel-ai-day1.zip
cd finsentinel-ai
code .
```

If the `code` command is unavailable, open VS Code and select **File → Open Folder → finsentinel-ai**.

## 2. Create local configuration

```bash
cp .env.example .env
```

## 3. Start the complete stack

Open Docker Desktop first, then run:

```bash
docker compose up --build
```

The first image download can take longer than later starts.

## 4. Verify the system

- Dashboard: http://localhost:3000
- API documentation: http://localhost:8000/docs
- API health: http://localhost:8000/health/live
- Grafana: http://localhost:3001 (`admin` / `admin`)
- Neo4j: http://localhost:7474 (`neo4j` / `finsentinel_dev`)
- Keycloak: http://localhost:8080 (`admin` / `admin`)

## 5. Test a high-risk investigation

Use the `/api/v1/investigations/run` endpoint in Swagger, or run:

```bash
curl -X POST http://localhost:8000/api/v1/investigations/run \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow": "fraud",
    "transaction": {
      "customer_id": "C-900",
      "account_id": "A-900",
      "merchant_id": "M-CRYPTO",
      "amount": "9750.00",
      "device_known": false,
      "ip_risk_score": 0.91,
      "merchant_risk_score": 0.89,
      "amount_zscore": 5.1,
      "velocity_1h": 11
    }
  }'
```

The Day-1 implementation returns a governed `block` or `manual_review` decision with four parallel agent findings and an audit identifier.

## 6. Stop services

```bash
docker compose down
```
