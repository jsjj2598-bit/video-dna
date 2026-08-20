from fastapi.testclient import TestClient

from app.main import app


def test_health_and_static_assets_are_available():
    client = TestClient(app)

    health = client.get("/health")

    assert health.status_code == 200
    assert health.json()["service"] == "video-dna-analyzer"
    assert health.json()["version"] == "0.3.1"
    assert client.get("/").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/js/core.js").status_code == 200


def test_component_api_never_returns_plaintext_keys():
    client = TestClient(app)

    response = client.get("/api/components")

    assert response.status_code == 200
    assert response.json()["models"]
    assert all("api_key" not in model for model in response.json()["models"])
