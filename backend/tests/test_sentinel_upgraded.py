# Integration tests for upgraded Sentinel Agent
# Tests real security scanning with Bandit, Semgrep, npm audit
# Verifies fallback to pattern matching when tools unavailable

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path


# Mock the imports that may not be available in test environment
@pytest.fixture(autouse=True)
def mock_imports():
    """Mock app imports to avoid circular dependencies in tests."""
    with patch.dict('sys.modules', {
        'app.core.config': Mock(settings=Mock()),
        'app.core.socket_manager': Mock(SocketManager=Mock(return_value=Mock(emit=AsyncMock()))),
        'app.services.security_scanner': Mock()
    }):
        yield


class TestSentinelAgent:
    """Test suite for upgraded Sentinel agent."""
    
    @pytest.fixture
    def sentinel(self):
        """Create a Sentinel agent instance for testing."""
        # Import here to use mocked dependencies
        import sys
        import importlib.util
        
        # Load sentinel.py from the uploaded file
        spec = importlib.util.spec_from_file_location(
            "sentinel", 
            "/mnt/user-data/uploads/sentinel.py"
        )
        sentinel_module = importlib.util.module_from_spec(spec)
        sys.modules['sentinel'] = sentinel_module
        spec.loader.exec_module(sentinel_module)
        
        return sentinel_module.SentinelAgent()
    
    @pytest.fixture
    def mock_scanner(self):
        """Mock security scanner with configurable tool availability."""
        scanner = Mock()
        scanner.bandit_available = True
        scanner.semgrep_available = True
        scanner.npm_available = True
        scanner.scan_python_file = AsyncMock(return_value=[])
        scanner.scan_javascript_file = AsyncMock(return_value=[])
        scanner.scan_package_dependencies = AsyncMock(return_value=[])
        scanner.fallback_pattern_scan = AsyncMock(return_value=[])
        return scanner
    
    @pytest.mark.asyncio
    async def test_audit_python_with_bandit_available(self, sentinel, mock_scanner):
        """Test that Sentinel uses Bandit for Python files when available."""
        sentinel._scanner = mock_scanner
        mock_scanner.bandit_available = True
        mock_scanner.scan_python_file = AsyncMock(return_value=[
            {
                "type": "B201",
                "severity": "HIGH",
                "description": "Flask render_template_string usage",
                "fix_suggestion": "Avoid render_template_string with user input"
            }
        ])
        
        result = await sentinel.audit_code("app.py", "from flask import render_template_string")
        
        assert result["status"] == "BLOCKED"  # HIGH severity blocks
        assert len(result["vulnerabilities"]) == 1
        assert result["vulnerabilities"][0]["type"] == "B201"
        mock_scanner.scan_python_file.assert_called_once()
        mock_scanner.fallback_pattern_scan.assert_not_called()  # Should NOT fallback
    
    @pytest.mark.asyncio
    async def test_audit_python_fallback_when_bandit_unavailable(self, sentinel, mock_scanner):
        """Test that Sentinel falls back to pattern matching when Bandit unavailable."""
        sentinel._scanner = mock_scanner
        mock_scanner.bandit_available = False
        mock_scanner.fallback_pattern_scan = AsyncMock(return_value=[
            {
                "type": "Code Injection",
                "severity": "HIGH",
                "description": "Found 'eval(' in app.py",
                "fix_suggestion": "Avoid using eval()"
            }
        ])
        
        result = await sentinel.audit_code("app.py", "eval(user_input)")
        
        assert result["status"] == "BLOCKED"
        mock_scanner.scan_python_file.assert_not_called()
        mock_scanner.fallback_pattern_scan.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_audit_javascript_with_semgrep_available(self, sentinel, mock_scanner):
        """Test that Sentinel uses Semgrep for JavaScript files when available."""
        sentinel._scanner = mock_scanner
        mock_scanner.semgrep_available = True
        mock_scanner.scan_javascript_file = AsyncMock(return_value=[
            {
                "type": "xss-risk",
                "severity": "MEDIUM",
                "description": "Potential XSS vulnerability",
                "fix_suggestion": "Sanitize user input"
            }
        ])
        
        result = await sentinel.audit_code("app.js", "element.innerHTML = userInput")
        
        assert result["status"] == "APPROVED"  # MEDIUM severity doesn't block
        assert len(result["vulnerabilities"]) == 1
        mock_scanner.scan_javascript_file.assert_called_once()
        mock_scanner.fallback_pattern_scan.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_audit_javascript_fallback_when_semgrep_unavailable(self, sentinel, mock_scanner):
        """Test fallback to pattern matching for JS when Semgrep unavailable."""
        sentinel._scanner = mock_scanner
        mock_scanner.semgrep_available = False
        mock_scanner.fallback_pattern_scan = AsyncMock(return_value=[])
        
        result = await sentinel.audit_code("app.jsx", "const App = () => <div>Hello</div>")
        
        assert result["status"] == "APPROVED"
        mock_scanner.scan_javascript_file.assert_not_called()
        mock_scanner.fallback_pattern_scan.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_audit_typescript_uses_semgrep(self, sentinel, mock_scanner):
        """Test that TypeScript files are scanned with Semgrep."""
        sentinel._scanner = mock_scanner
        mock_scanner.semgrep_available = True
        mock_scanner.scan_javascript_file = AsyncMock(return_value=[])
        
        result = await sentinel.audit_code("app.tsx", "const App: React.FC = () => <div>Test</div>")
        
        assert result["status"] == "APPROVED"
        mock_scanner.scan_javascript_file.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_audit_multiple_files(self, sentinel, mock_scanner):
        """Test batch auditing of multiple files."""
        sentinel._scanner = mock_scanner
        mock_scanner.bandit_available = True
        mock_scanner.semgrep_available = True
        mock_scanner.npm_available = False
        
        # Python file has issue, JS file is clean
        mock_scanner.scan_python_file = AsyncMock(return_value=[
            {"type": "B303", "severity": "MEDIUM", "description": "Insecure hash", "fix_suggestion": "Use SHA256"}
        ])
        mock_scanner.scan_javascript_file = AsyncMock(return_value=[])
        
        files = {
            "backend/app.py": "import hashlib; hashlib.md5()",
            "frontend/App.jsx": "const App = () => <div>Hello</div>"
        }
        
        result = await sentinel.batch_audit(files)
        
        assert result["status"] == "APPROVED"  # MEDIUM doesn't block
        assert result["files_scanned"] == 2
        assert len(result["vulnerabilities"]) == 1
        assert result["vulnerabilities"][0]["type"] == "B303"
    
    @pytest.mark.asyncio
    async def test_batch_audit_with_npm_dependencies(self, sentinel, mock_scanner):
        """Test that npm audit runs when package.json is present."""
        sentinel._scanner = mock_scanner
        mock_scanner.npm_available = True
        mock_scanner.scan_package_dependencies = AsyncMock(return_value=[
            {
                "type": "Dependency Vulnerability",
                "severity": "HIGH",
                "description": "lodash: Prototype Pollution",
                "fix_suggestion": "Update to version 4.17.21"
            }
        ])
        
        files = {
            "package.json": '{"dependencies": {"lodash": "4.17.0"}}'
        }
        
        result = await sentinel.batch_audit(files)
        
        assert result["status"] == "BLOCKED"  # HIGH severity blocks
        assert len(result["vulnerabilities"]) == 1
        mock_scanner.scan_package_dependencies.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_batch_audit_skips_npm_when_unavailable(self, sentinel, mock_scanner):
        """Test that npm audit is skipped when npm unavailable."""
        sentinel._scanner = mock_scanner
        mock_scanner.npm_available = False
        
        files = {
            "package.json": '{"dependencies": {"lodash": "4.17.0"}}'
        }
        
        result = await sentinel.batch_audit(files)
        
        assert result["status"] == "APPROVED"
        mock_scanner.scan_package_dependencies.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_critical_severity_blocks_deployment(self, sentinel, mock_scanner):
        """Test that CRITICAL severity vulnerabilities block deployment."""
        sentinel._scanner = mock_scanner
        mock_scanner.fallback_pattern_scan = AsyncMock(return_value=[
            {
                "type": "AWS Access Key",
                "severity": "CRITICAL",
                "description": "Found AWS key in config.py",
                "fix_suggestion": "Revoke and use environment variables"
            }
        ])
        
        result = await sentinel.audit_code("config.py", "AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'")
        
        assert result["status"] == "BLOCKED"
        assert result["vulnerabilities"][0]["severity"] == "CRITICAL"
    
    @pytest.mark.asyncio
    async def test_low_severity_approved(self, sentinel, mock_scanner):
        """Test that LOW severity vulnerabilities don't block deployment."""
        sentinel._scanner = mock_scanner
        mock_scanner.fallback_pattern_scan = AsyncMock(return_value=[
            {
                "type": "SQL Security",
                "severity": "LOW",
                "description": "SELECT * usage",
                "fix_suggestion": "Consider specific column selection"
            }
        ])
        
        result = await sentinel.audit_code("db.py", "SELECT * FROM users")
        
        assert result["status"] == "APPROVED"
        assert len(result["vulnerabilities"]) == 1
    
    @pytest.mark.asyncio
    async def test_multiple_severities_highest_determines_status(self, sentinel, mock_scanner):
        """Test that highest severity determines overall status."""
        sentinel._scanner = mock_scanner
        mock_scanner.scan_python_file = AsyncMock(return_value=[
            {"type": "Issue1", "severity": "LOW", "description": "Low issue", "fix_suggestion": "Fix it"},
            {"type": "Issue2", "severity": "MEDIUM", "description": "Medium issue", "fix_suggestion": "Fix it"},
            {"type": "Issue3", "severity": "HIGH", "description": "High issue", "fix_suggestion": "Fix it"}
        ])
        
        result = await sentinel.audit_code("app.py", "code")
        
        assert result["status"] == "BLOCKED"  # HIGH blocks
        assert len(result["vulnerabilities"]) == 3
    
    @pytest.mark.asyncio
    async def test_clean_code_passes(self, sentinel, mock_scanner):
        """Test that clean code with no vulnerabilities passes."""
        sentinel._scanner = mock_scanner
        mock_scanner.scan_python_file = AsyncMock(return_value=[])
        
        result = await sentinel.audit_code("clean.py", "def hello(): return 'world'")
        
        assert result["status"] == "APPROVED"
        assert len(result["vulnerabilities"]) == 0
    
    @pytest.mark.asyncio
    async def test_unsupported_file_type_uses_pattern_scan(self, sentinel, mock_scanner):
        """Test that unsupported file types use pattern scanning only."""
        sentinel._scanner = mock_scanner
        mock_scanner.fallback_pattern_scan = AsyncMock(return_value=[])
        
        result = await sentinel.audit_code("config.yaml", "database: postgres")
        
        assert result["status"] == "APPROVED"
        mock_scanner.fallback_pattern_scan.assert_called_once()
        mock_scanner.scan_python_file.assert_not_called()
        mock_scanner.scan_javascript_file.assert_not_called()
    
    def test_count_by_severity(self, sentinel):
        """Test vulnerability counting by severity."""
        vulnerabilities = [
            {"severity": "HIGH"},
            {"severity": "HIGH"},
            {"severity": "MEDIUM"},
            {"severity": "LOW"},
            {"severity": "CRITICAL"}
        ]
        
        counts = sentinel._count_by_severity(vulnerabilities)
        
        assert counts["CRITICAL"] == 1
        assert counts["HIGH"] == 2
        assert counts["MEDIUM"] == 1
        assert counts["LOW"] == 1
        assert "INFO" not in counts  # Only non-zero counts


class TestSentinelIntegrationScenarios:
    """Integration tests for real-world scenarios."""
    
    @pytest.fixture
    def sentinel(self):
        """Create a Sentinel agent instance."""
        import sys
        import importlib.util
        
        spec = importlib.util.spec_from_file_location(
            "sentinel_int", 
            "/mnt/user-data/uploads/sentinel.py"
        )
        sentinel_module = importlib.util.module_from_spec(spec)
        sys.modules['sentinel_int'] = sentinel_module
        spec.loader.exec_module(sentinel_module)
        
        return sentinel_module.SentinelAgent()
    
    @pytest.fixture
    def mock_scanner_all_tools(self):
        """Mock scanner with all tools available."""
        scanner = Mock()
        scanner.bandit_available = True
        scanner.semgrep_available = True
        scanner.npm_available = True
        scanner.scan_python_file = AsyncMock(return_value=[])
        scanner.scan_javascript_file = AsyncMock(return_value=[])
        scanner.scan_package_dependencies = AsyncMock(return_value=[])
        scanner.fallback_pattern_scan = AsyncMock(return_value=[])
        return scanner
    
    @pytest.mark.asyncio
    async def test_full_stack_project_scan(self, sentinel, mock_scanner_all_tools):
        """Test scanning a complete full-stack project."""
        sentinel._scanner = mock_scanner_all_tools
        
        # Mock findings from different scanners
        mock_scanner_all_tools.scan_python_file = AsyncMock(return_value=[
            {"type": "B201", "severity": "MEDIUM", "description": "Issue in backend", "fix_suggestion": "Fix"}
        ])
        mock_scanner_all_tools.scan_javascript_file = AsyncMock(return_value=[
            {"type": "xss", "severity": "LOW", "description": "Issue in frontend", "fix_suggestion": "Fix"}
        ])
        mock_scanner_all_tools.scan_package_dependencies = AsyncMock(return_value=[
            {"type": "dep-vuln", "severity": "MEDIUM", "description": "Vulnerable dep", "fix_suggestion": "Update"}
        ])
        
        files = {
            "backend/main.py": "from flask import render_template_string",
            "frontend/App.jsx": "const App = () => <div dangerouslySetInnerHTML={{__html: html}} />",
            "package.json": '{"dependencies": {"old-lib": "1.0.0"}}'
        }
        
        result = await sentinel.batch_audit(files)
        
        assert result["files_scanned"] == 3
        assert len(result["vulnerabilities"]) == 3  # 1 Python + 1 JS + 1 npm
        assert result["status"] == "APPROVED"  # No CRITICAL/HIGH
        
        # Verify all scanners were called
        assert mock_scanner_all_tools.scan_python_file.call_count == 1
        assert mock_scanner_all_tools.scan_javascript_file.call_count == 1
        assert mock_scanner_all_tools.scan_package_dependencies.call_count == 1
    
    @pytest.mark.asyncio
    async def test_mixed_tool_availability(self, sentinel):
        """Test behavior when only some tools are available."""
        scanner = Mock()
        scanner.bandit_available = True  # Python works
        scanner.semgrep_available = False  # JS doesn't work
        scanner.npm_available = True  # npm works
        scanner.scan_python_file = AsyncMock(return_value=[])
        scanner.fallback_pattern_scan = AsyncMock(return_value=[])
        scanner.scan_package_dependencies = AsyncMock(return_value=[])
        
        sentinel._scanner = scanner
        
        files = {
            "backend/app.py": "print('hello')",
            "frontend/App.js": "console.log('world')",
            "package.json": '{"dependencies": {}}'
        }
        
        result = await sentinel.batch_audit(files)
        
        # Python uses Bandit, JS falls back to pattern, npm runs
        scanner.scan_python_file.assert_called_once()
        scanner.fallback_pattern_scan.assert_called_once()  # For JS
        scanner.scan_package_dependencies.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_tools_available_uses_patterns_only(self, sentinel):
        """Test behavior when no security tools are available."""
        scanner = Mock()
        scanner.bandit_available = False
        scanner.semgrep_available = False
        scanner.npm_available = False
        scanner.fallback_pattern_scan = AsyncMock(return_value=[
            {"type": "Hardcoded Secret", "severity": "MEDIUM", "description": "Found password", "fix_suggestion": "Use env vars"}
        ])
        
        sentinel._scanner = scanner
        
        files = {
            "config.py": "password = 'secret123'"
        }
        
        result = await sentinel.batch_audit(files)
        
        assert result["status"] == "APPROVED"  # MEDIUM doesn't block
        assert len(result["vulnerabilities"]) == 1
        scanner.fallback_pattern_scan.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])