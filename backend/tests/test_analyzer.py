# backend/tests/test_analyzer.py
import pytest
import os
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from app.agents.analyzer import AnalyzerAgent

# Use a temporary directory for tests
TEST_REPO_DIR = Path("tmp_test_analyzer_repo")

def _force_remove_readonly(func, path, exc_info):
    import stat
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    if TEST_REPO_DIR.exists():
        shutil.rmtree(TEST_REPO_DIR, onerror=_force_remove_readonly)
    TEST_REPO_DIR.mkdir()
    
    yield
    
    # Teardown
    if TEST_REPO_DIR.exists():
        try:
            shutil.rmtree(TEST_REPO_DIR, onerror=_force_remove_readonly)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_build_file_tree():
    agent = AnalyzerAgent()
    
    # Create structure
    (TEST_REPO_DIR / "src").mkdir()
    (TEST_REPO_DIR / "src" / "main.py").write_text("print('hello')")
    (TEST_REPO_DIR / "README.md").write_text("# Test Repo")
    
    tree = agent._build_file_tree(TEST_REPO_DIR)
    
    assert "📄 README.md" in tree
    assert "📁 src/" in tree
    assert "📄 main.py" in tree

@pytest.mark.asyncio
async def test_identify_key_files():
    agent = AnalyzerAgent()
    
    # Create key files
    (TEST_REPO_DIR / "package.json").write_text("{}")
    (TEST_REPO_DIR / "Dockerfile").write_text("FROM python:3.9")
    (TEST_REPO_DIR / "src").mkdir()
    (TEST_REPO_DIR / "src" / "app.py").write_text("# Entry")
    
    key_files = agent._identify_key_files(TEST_REPO_DIR)
    
    # Check absolute paths presence by converting to relative logic or just key existence
    # The method returns absolute paths in values, but keys are filenames or rel paths
    
    assert "package.json" in key_files
    assert "Dockerfile" in key_files
    
    # Entry point detection might return relative path
    # Windows path separator might vary, checking if value points to correct file
    found_app = False
    for k, v in key_files.items():
        if "app.py" in k:
            found_app = True
            break
    assert found_app

@pytest.mark.asyncio
async def test_detect_tech_stack():
    agent = AnalyzerAgent()
    
    # Create Python/FastAPI setup
    (TEST_REPO_DIR / "requirements.txt").write_text("fastapi==0.100.0\nuvicorn")
    (TEST_REPO_DIR / "Dockerfile").write_text("FROM python")
    
    key_files = {
        "requirements.txt": str(TEST_REPO_DIR / "requirements.txt"),
        "Dockerfile": str(TEST_REPO_DIR / "Dockerfile")
    }
    
    stack = agent._detect_tech_stack(TEST_REPO_DIR, key_files)
    
    assert "Python" in stack["languages"]
    assert "FastAPI" in stack["frameworks"]
    assert "Docker" in stack["tools"]

@pytest.mark.asyncio
@patch("app.core.HybridModelClient.HybridModelClient")
@patch("app.core.key_manager.KeyManager")
async def test_analyze_codebase_mock_llm(MockKeyManager, MockClient):
    # Setup Mock
    mock_instance = MockClient.return_value
    mock_instance.generate = AsyncMock(return_value='```json\n{"relevant_files": ["main.py"], "risks": ["none"]}\n```')
    
    agent = AnalyzerAgent()
    
    # Create repo content
    (TEST_REPO_DIR / "main.py").write_text("print('hello')")
    
    result = await agent.analyze_codebase(str(TEST_REPO_DIR), "Understand structure")
    
    assert result["success"] is True
    assert "file_tree" in result
    assert "gemini_analysis" in result
    assert result["gemini_analysis"]["relevant_files"] == ["main.py"]
