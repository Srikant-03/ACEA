
import os
import tempfile
import pytest
from app.core.config import settings
from app.api.endpoints import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_config_fixes():
    """Verify Phase 1 config fixes."""
    # check PROJECTS_DIR uses tempfile
    expected_root = tempfile.gettempdir()
    assert str(settings.PROJECTS_DIR).startswith(expected_root), \
        f"PROJECTS_DIR {settings.PROJECTS_DIR} should start with tempdir {expected_root}"

    # check JWT_SECRET loaded from env or default
    # In test env, it might be default unless set
    assert settings.JWT_SECRET is not None

def test_debug_endpoint_missing_project():
    """Verify debug endpoint returns 404 for missing project."""
    response = client.post("/debug/non_existent_project_id_12345")
    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]

def test_generate_docs_endpoint_missing_project():
    """Verify generate-docs endpoint returns 404 for missing project."""
    response = client.post("/generate-docs/non_existent_project_id_12345")
    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]

def test_model_client_delegation():
    """Verify local_model.HybridModelClient delegates to core client."""
    from app.core.local_model import HybridModelClient
    
    # Mock the core client to avoid actual API calls
    class MockCoreClient:
        async def generate(self, prompt):
            class Response:
                output = "Mocked Cloud Response"
            return Response()

    client = HybridModelClient_Class = HybridModelClient()
    client._core_client = MockCoreClient()
    
    # Test delegation
    import asyncio
    response = asyncio.run(client.generate("Test prompt"))
    assert response == "Mocked Cloud Response"

