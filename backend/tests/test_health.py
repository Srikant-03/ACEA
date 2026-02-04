import pytest
import httpx
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_sync():
    response = client.get("/health")
    # It might return 200 or the exact JSON, just check status for now
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_health_check_async():
    async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
