from fastapi.testclient import TestClient

from getsinapi.api.main import app

client = TestClient(app)


def test_health_endpoint_reports_api_availability_only():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "get-sinapi-api",
        "version": "0.1.0",
    }
