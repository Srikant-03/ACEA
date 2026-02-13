# Integration tests for Testing Agent
# Tests test generation, multi-framework support, and test execution

import pytest
import asyncio
import os
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path


class TestTestingAgent:
    """Test suite for TestingAgent."""
    
    @pytest.fixture
    def testing_agent(self):
        """Create a TestingAgent instance for testing."""
        import sys
        import importlib.util
        
        # Mock dependencies
        with patch.dict('sys.modules', {
            'app.core.config': Mock(settings=Mock()),
            'app.core.socket_manager': Mock(SocketManager=Mock(return_value=Mock(emit=AsyncMock()))),
            'app.core.local_model': Mock()
        }):
            spec = importlib.util.spec_from_file_location(
                "testing_agent",
                "/mnt/user-data/uploads/testing_agent.py"
            )
            agent_module = importlib.util.module_from_spec(spec)
            sys.modules['testing_agent'] = agent_module
            spec.loader.exec_module(agent_module)
            
            return agent_module.TestingAgent()
    
    @pytest.mark.asyncio
    async def test_detect_framework_pytest_for_python(self, testing_agent):
        """Test framework detection for Python projects."""
        file_system = {
            "backend/main.py": "print('hello')",
            "backend/models.py": "class User: pass"
        }
        
        framework = await testing_agent._detect_framework("/project", file_system, "Python")
        
        assert framework == "pytest"
    
    @pytest.mark.asyncio
    async def test_detect_framework_vitest_from_package_json(self, testing_agent):
        """Test framework detection from package.json dependencies."""
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                    "devDependencies": {"vitest": "^0.34.0"}
                })
                
                file_system = {"frontend/App.jsx": "const App = () => {}"}
                
                framework = await testing_agent._detect_framework("/project", file_system, "React")
                
                assert framework == "vitest"
    
    @pytest.mark.asyncio
    async def test_detect_framework_jest_from_package_json(self, testing_agent):
        """Test Jest detection from package.json."""
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                    "devDependencies": {"jest": "^29.0.0"}
                })
                
                file_system = {"frontend/App.js": "const App = () => {}"}
                
                framework = await testing_agent._detect_framework("/project", file_system, "JavaScript")
                
                assert framework == "jest"
    
    @pytest.mark.asyncio
    async def test_detect_framework_defaults_to_vitest_for_vite(self, testing_agent):
        """Test that Vite projects default to Vitest."""
        with patch('os.path.exists', return_value=False):
            file_system = {"frontend/App.jsx": "const App = () => {}"}
            
            framework = await testing_agent._detect_framework("/project", file_system, "Vite + React")
            
            assert framework == "vitest"
    
    def test_find_testable_files_includes_source_code(self, testing_agent):
        """Test that testable files include only source code."""
        file_system = {
            "backend/main.py": "def main(): pass",
            "backend/models.py": "class User: pass",
            "frontend/App.jsx": "const App = () => <div>Hello</div>",
            "frontend/utils.js": "export const add = (a, b) => a + b"
        }
        
        testable = testing_agent._find_testable_files(file_system)
        
        assert "backend/main.py" in testable
        assert "backend/models.py" in testable
        assert "frontend/App.jsx" in testable
        assert "frontend/utils.js" in testable
        assert len(testable) == 4
    
    def test_find_testable_files_excludes_configs(self, testing_agent):
        """Test that config files are excluded from testing."""
        file_system = {
            "backend/main.py": "def main(): pass",
            "package.json": '{"name": "test"}',
            "tsconfig.json": '{"compilerOptions": {}}',
            "vite.config.js": 'export default {}',
            "tailwind.config.js": 'module.exports = {}'
        }
        
        testable = testing_agent._find_testable_files(file_system)
        
        assert "backend/main.py" in testable
        assert "package.json" not in testable
        assert "tsconfig.json" not in testable
        assert "vite.config.js" not in testable
        assert "tailwind.config.js" not in testable
    
    def test_find_testable_files_excludes_existing_tests(self, testing_agent):
        """Test that existing test files are excluded."""
        file_system = {
            "backend/main.py": "def main(): pass",
            "backend/test_main.py": "def test_main(): pass",
            "frontend/App.jsx": "const App = () => {}",
            "frontend/App.test.jsx": "test('renders', () => {})",
            "frontend/__tests__/utils.spec.js": "describe('utils', () => {})"
        }
        
        testable = testing_agent._find_testable_files(file_system)
        
        assert "backend/main.py" in testable
        assert "frontend/App.jsx" in testable
        assert "backend/test_main.py" not in testable
        assert "frontend/App.test.jsx" not in testable
        assert "frontend/__tests__/utils.spec.js" not in testable
    
    def test_find_testable_files_excludes_build_outputs(self, testing_agent):
        """Test that build outputs and dependencies are excluded."""
        file_system = {
            "backend/main.py": "def main(): pass",
            "node_modules/react/index.js": "// React",
            "dist/bundle.js": "// Bundle",
            "build/index.html": "<html></html>",
            ".next/server.js": "// Next",
            "__pycache__/main.cpython-39.pyc": "binary"
        }
        
        testable = testing_agent._find_testable_files(file_system)
        
        assert "backend/main.py" in testable
        assert len(testable) == 1  # Only main.py
    
    def test_find_testable_files_excludes_empty_files(self, testing_agent):
        """Test that very small/empty files are excluded."""
        file_system = {
            "backend/main.py": "def main():\n    return 'Hello, world!'\n\nif __name__ == '__main__':\n    main()",
            "backend/empty.py": "",
            "backend/tiny.py": "# TODO",
            "frontend/App.jsx": "import React from 'react';\n\nconst App = () => <div>Hello</div>;\n\nexport default App;"
        }
        
        testable = testing_agent._find_testable_files(file_system)
        
        assert "backend/main.py" in testable
        assert "frontend/App.jsx" in testable
        assert "backend/empty.py" not in testable
        assert "backend/tiny.py" not in testable
    
    def test_get_language_python(self, testing_agent):
        """Test language detection for Python."""
        assert testing_agent._get_language("app.py") == "python"
        assert testing_agent._get_language("backend/models.py") == "python"
    
    def test_get_language_javascript(self, testing_agent):
        """Test language detection for JavaScript."""
        assert testing_agent._get_language("app.js") == "javascript"
        assert testing_agent._get_language("utils.jsx") == "javascript"
    
    def test_get_language_typescript(self, testing_agent):
        """Test language detection for TypeScript."""
        assert testing_agent._get_language("app.ts") == "typescript"
        assert testing_agent._get_language("Component.tsx") == "typescript"
    
    def test_get_test_file_path_pytest(self, testing_agent):
        """Test test file path generation for pytest."""
        source_path = "backend/models.py"
        test_path = testing_agent._get_test_file_path(source_path, "pytest")
        
        assert test_path == "backend/tests/test_models.py"
    
    def test_get_test_file_path_vitest(self, testing_agent):
        """Test test file path generation for Vitest."""
        source_path = "frontend/components/Button.tsx"
        test_path = testing_agent._get_test_file_path(source_path, "vitest")
        
        assert test_path == "frontend/__tests__/Button.test.tsx"
    
    def test_get_test_file_path_jest(self, testing_agent):
        """Test test file path generation for Jest."""
        source_path = "frontend/utils/helpers.js"
        test_path = testing_agent._get_test_file_path(source_path, "jest")
        
        assert test_path == "frontend/__tests__/helpers.test.js"
    
    def test_clean_generated_code_removes_markdown(self, testing_agent):
        """Test that markdown code fences are removed from generated code."""
        llm_output = """```python
def test_add():
    assert add(1, 2) == 3
```"""
        
        cleaned = testing_agent._clean_generated_code(llm_output, "python")
        
        assert "```" not in cleaned
        assert "def test_add():" in cleaned
    
    def test_clean_generated_code_removes_preamble(self, testing_agent):
        """Test that explanatory preambles are removed."""
        llm_output = """Here are the tests for your code:

```python
def test_add():
    assert add(1, 2) == 3
```

These tests cover the basic functionality."""
        
        cleaned = testing_agent._clean_generated_code(llm_output, "python")
        
        assert "Here are the tests" not in cleaned
        assert "These tests cover" not in cleaned
        assert "def test_add():" in cleaned
    
    @pytest.mark.asyncio
    async def test_generate_tests_creates_test_files(self, testing_agent):
        """Test that generate_tests creates test files for each source file."""
        mock_client = Mock()
        mock_client.generate = AsyncMock(return_value="def test_example(): assert True")
        
        with patch('app.core.local_model.HybridModelClient', return_value=mock_client):
            mock_sm = Mock(emit=AsyncMock())
            
            file_system = {
                "backend/main.py": "def main(): return 'hello'",
                "backend/utils.py": "def add(a, b): return a + b"
            }
            
            test_files = await testing_agent._generate_tests(file_system, "pytest", mock_sm)
            
            # Should generate tests for both files
            assert len(test_files) == 2
            assert "backend/tests/test_main.py" in test_files
            assert "backend/tests/test_utils.py" in test_files
            assert mock_client.generate.call_count == 2
    
    @pytest.mark.asyncio
    async def test_generate_tests_handles_llm_errors(self, testing_agent):
        """Test that generate_tests handles LLM errors gracefully."""
        mock_client = Mock()
        mock_client.generate = AsyncMock(side_effect=Exception("API Error"))
        
        with patch('app.core.local_model.HybridModelClient', return_value=mock_client):
            mock_sm = Mock(emit=AsyncMock())
            
            file_system = {"backend/main.py": "def main(): pass"}
            
            test_files = await testing_agent._generate_tests(file_system, "pytest", mock_sm)
            
            # Should return empty dict on error
            assert test_files == {}
    
    @pytest.mark.asyncio
    async def test_write_test_files_creates_directories(self, testing_agent):
        """Test that write_test_files creates necessary directories."""
        mock_sm = Mock(emit=AsyncMock())
        test_files = {
            "backend/tests/test_main.py": "def test_main(): pass"
        }
        
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            with patch('pathlib.Path.write_text') as mock_write:
                await testing_agent._write_test_files("/project", test_files, mock_sm)
                
                mock_mkdir.assert_called()
                mock_write.assert_called()
    
    @pytest.mark.asyncio
    async def test_run_pytest_parses_output(self, testing_agent):
        """Test that pytest runner parses test results correctly."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """
test_main.py::test_example PASSED
test_utils.py::test_add PASSED
test_utils.py::test_subtract PASSED
"""
        mock_result.stderr = ""
        
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('subprocess.run', return_value=mock_result):
            with patch('os.path.exists', return_value=True):
                result = await testing_agent._run_pytest("/project", mock_sm)
                
                assert result["success"] is True
                assert result["framework"] == "pytest"
                assert result["passed"] == 3
                assert result["failed"] == 0
    
    @pytest.mark.asyncio
    async def test_run_pytest_handles_failures(self, testing_agent):
        """Test that pytest runner handles test failures."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = """
test_main.py::test_example PASSED
test_utils.py::test_add FAILED
test_utils.py::test_subtract SKIPPED
"""
        mock_result.stderr = ""
        
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('subprocess.run', return_value=mock_result):
            with patch('os.path.exists', return_value=True):
                result = await testing_agent._run_pytest("/project", mock_sm)
                
                assert result["success"] is False
                assert result["passed"] == 1
                assert result["failed"] == 1
                assert result["skipped"] == 1
    
    @pytest.mark.asyncio
    async def test_run_pytest_handles_timeout(self, testing_agent):
        """Test that pytest runner handles timeout gracefully."""
        import subprocess
        
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('pytest', 30)):
            with patch('os.path.exists', return_value=True):
                result = await testing_agent._run_pytest("/project", mock_sm)
                
                assert result["success"] is False
                assert "timed out" in result["error"]
    
    @pytest.mark.asyncio
    async def test_run_pytest_handles_missing_backend(self, testing_agent):
        """Test pytest runner handles missing backend directory."""
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('os.path.exists', return_value=False):
            result = await testing_agent._run_pytest("/project", mock_sm)
            
            assert result["success"] is False
            assert "backend" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_run_vitest_parses_output(self, testing_agent):
        """Test that Vitest runner parses test results."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """
 ✓ App.test.jsx (3)
   ✓ renders correctly
   ✓ handles click
   ✓ updates state
"""
        mock_result.stderr = ""
        
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('subprocess.run', return_value=mock_result):
            with patch('os.path.exists', return_value=True):
                result = await testing_agent._run_vitest("/project", mock_sm)
                
                assert result["success"] is True
                assert result["framework"] == "vitest"
                assert result["passed"] == 3
    
    @pytest.mark.asyncio
    async def test_run_jest_parses_output(self, testing_agent):
        """Test that Jest runner parses test results."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = """
Test Suites: 2 passed, 2 total
Tests:       5 passed, 5 total
"""
        mock_result.stderr = ""
        
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('subprocess.run', return_value=mock_result):
            with patch('os.path.exists', return_value=True):
                result = await testing_agent._run_jest("/project", mock_sm)
                
                assert result["success"] is True
                assert result["framework"] == "jest"
                assert result["passed"] == 5
    
    @pytest.mark.asyncio
    async def test_quick_validate_detects_test_directories(self, testing_agent):
        """Test quick validation detects test directories."""
        mock_sm = Mock(emit=AsyncMock())
        
        with patch('os.path.exists', side_effect=[True, False]):  # backend exists, frontend doesn't
            with patch('os.listdir', return_value=['test_main.py', 'test_utils.py']):
                result = await testing_agent.quick_validate("/project", mock_sm)
                
                assert result["has_tests"] is True
                assert result["backend_tests"] is True
                assert result["frontend_tests"] is False


class TestTestingAgentIntegration:
    """Integration tests for real-world testing scenarios."""
    
    @pytest.fixture
    def testing_agent(self):
        """Create testing agent instance."""
        import sys
        import importlib.util
        
        with patch.dict('sys.modules', {
            'app.core.config': Mock(settings=Mock()),
            'app.core.socket_manager': Mock(SocketManager=Mock(return_value=Mock(emit=AsyncMock()))),
            'app.core.local_model': Mock()
        }):
            spec = importlib.util.spec_from_file_location(
                "testing_agent_int",
                "/mnt/user-data/uploads/testing_agent.py"
            )
            agent_module = importlib.util.module_from_spec(spec)
            sys.modules['testing_agent_int'] = agent_module
            spec.loader.exec_module(agent_module)
            
            return agent_module.TestingAgent()
    
    @pytest.mark.asyncio
    async def test_full_python_project_workflow(self, testing_agent):
        """Test complete workflow for Python project."""
        mock_client = Mock()
        mock_client.generate = AsyncMock(return_value="def test_example(): assert True")
        
        mock_sm = Mock(emit=AsyncMock())
        
        file_system = {
            "backend/main.py": "def main(): return 'hello'",
            "backend/utils.py": "def add(a, b): return a + b"
        }
        
        with patch('app.core.local_model.HybridModelClient', return_value=mock_client):
            with patch('os.path.exists', return_value=False):
                framework = await testing_agent._detect_framework("/project", file_system, "Python")
                
                assert framework == "pytest"
                
                test_files = await testing_agent._generate_tests(file_system, framework, mock_sm)
                
                assert len(test_files) == 2
    
    @pytest.mark.asyncio
    async def test_full_javascript_project_workflow(self, testing_agent):
        """Test complete workflow for JavaScript project."""
        mock_client = Mock()
        mock_client.generate = AsyncMock(return_value="test('works', () => { expect(true).toBe(true); });")
        
        mock_sm = Mock(emit=AsyncMock())
        
        file_system = {
            "frontend/App.jsx": "const App = () => <div>Hello</div>",
            "frontend/utils.js": "export const add = (a, b) => a + b"
        }
        
        with patch('app.core.local_model.HybridModelClient', return_value=mock_client):
            with patch('os.path.exists', return_value=False):
                framework = await testing_agent._detect_framework("/project", file_system, "React")
                
                test_files = await testing_agent._generate_tests(file_system, framework, mock_sm)
                
                assert len(test_files) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
    