from httpx import AsyncClient


async def test_health_returns_status_version_env(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "test"
    assert body["env"] == "stage"


async def test_sync_returns_503_without_ynab_token(client: AsyncClient) -> None:
    response = await client.post("/sync")
    assert response.status_code == 503
    assert "YNAB_TOKEN" in response.json()["detail"]
