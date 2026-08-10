from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_request_is_observable() -> None:
    response = client.get(
        "/health/live"
    )

    assert response.status_code == 200

    metrics = client.get(
        "/metrics"
    )

    assert metrics.status_code == 200

    body = metrics.text

    assert (
        "finsentinel_http_requests_total"
        in body
    )

    assert (
        "finsentinel_http_request_duration_seconds"
        in body
    )

    assert (
        "finsentinel_http_active_requests"
        in body
    )


def test_unauthorized_request_is_counted() -> None:
    response = client.get(
        "/api/v1/security/me"
    )

    assert response.status_code == 401

    metrics = client.get(
        "/metrics"
    )

    assert (
        "finsentinel_http_errors_total"
        in metrics.text
    )
