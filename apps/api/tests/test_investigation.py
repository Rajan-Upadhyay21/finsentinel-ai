from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_parallel_investigation_contract() -> None:
    response = client.post(
        "/api/v1/investigations/run",
        json={
            "workflow": "fraud",
            "transaction": {
                "customer_id": "C-777",
                "account_id": "A-777",
                "merchant_id": "M-777",
                "amount": str(Decimal("8200.00")),
                "device_known": False,
                "ip_risk_score": 0.87,
                "merchant_risk_score": 0.78,
                "amount_zscore": 4.4,
                "velocity_1h": 9
            }
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["findings"]) == 4
    assert payload["decision"] in {"manual_review", "block"}
    assert payload["audit_id"]
