from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.core.security import AuthenticatedUser, get_current_user


def _authenticated_fraud_analyst() -> AuthenticatedUser:
    return AuthenticatedUser(
        subject="test-fraud-analyst-subject",
        username="test-fraud-analyst",
        email="fraud.analyst@example.test",
        roles=frozenset(
            {
                "fraud_analyst",
            }
        ),
    )



@pytest.fixture
def fraud_analyst_auth():
    app.dependency_overrides[
        get_current_user
    ] = _authenticated_fraud_analyst

    try:
        yield
    finally:
        app.dependency_overrides.pop(
            get_current_user,
            None,
        )


client = TestClient(app)


def test_parallel_investigation_contract(fraud_analyst_auth) -> None:
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
