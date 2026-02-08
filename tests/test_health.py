#Tests for the health endpoint.
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_check():
#Test that health endpoint returns 200 and healthy status.
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_check_response_structure():
    #Test that health endpoint returns expected fields.
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert "version" in data
    assert "debug" in data
