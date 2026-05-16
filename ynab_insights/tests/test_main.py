from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_hello_payload() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Hello"
    assert "version" in body
    assert "env" in body


def test_root_reflects_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("APP_ENV", "prod")
    response = client.get("/")
    body = response.json()
    assert body["version"] == "1.2.3"
    assert body["env"] == "prod"


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
