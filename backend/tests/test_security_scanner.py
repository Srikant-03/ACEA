# Integration tests for Security Scanner Service
# Tests Bandit, Semgrep, npm audit wrappers and fallback patterns

import pytest
import asyncio
import json
import subprocess
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


class TestSecurityScanner:
    """Test suite for SecurityScanner service."""
    
    @pytest.fixture
    def scanner(self):
        """Create a SecurityScanner instance for testing."""
        import sys
        import importlib.util
        
        # Load security_scanner.py from uploaded file
        spec = importlib.util.spec_from_file_location(
            "security_scanner",
            "/mnt/user-data/uploads/security_scanner.py"
        )
        scanner_module = importlib.util.module_from_spec(spec)
        sys.modules['security_scanner'] = scanner_module
        spec.loader.exec_module(scanner_module)
        
        return scanner_module.SecurityScanner()
    
    def test_check_tool_available(self, scanner):
        """Test tool availability checking."""
        # This will vary by environment, but we can test the method exists
        assert hasattr(scanner, '_check_tool')
        assert isinstance(scanner.bandit_available, bool)
        assert isinstance(scanner.semgrep_available, bool)
        assert isinstance(scanner.npm_available, bool)
    
    @pytest.mark.asyncio
    async def test_scan_python_file_with_bandit(self, scanner):
        """Test Python scanning with Bandit (if available)."""
        if not scanner.bandit_available:
            pytest.skip("Bandit not installed")
        
        # Test code with known vulnerability
        vulnerable_code = """
import pickle
import os

def load_data(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)  # B301: Pickle usage

def run_command(cmd):
    os.system(cmd)  # B605: Shell command
"""
        
        vulnerabilities = await scanner.scan_python_file("test.py", vulnerable_code)
        
        # Should detect pickle and os.system issues
        assert len(vulnerabilities) > 0
        
        # Check structure
        for vuln in vulnerabilities:
            assert "type" in vuln
            assert "severity" in vuln
            assert "description" in vuln
            assert "fix_suggestion" in vuln
            assert vuln["severity"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    
    @pytest.mark.asyncio
    async def test_scan_python_file_clean_code(self, scanner):
        """Test Python scanning with clean code."""
        if not scanner.bandit_available:
            pytest.skip("Bandit not installed")
        
        clean_code = """
def add(a, b):
    return a + b

def greet(name):
    return f"Hello, {name}!"
"""
        
        vulnerabilities = await scanner.scan_python_file("clean.py", clean_code)
        
        # Clean code should have no or minimal vulnerabilities
        assert isinstance(vulnerabilities, list)
    
    @pytest.mark.asyncio
    async def test_scan_python_handles_timeout(self, scanner):
        """Test that Python scanning handles timeouts gracefully."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('bandit', 30)):
            vulnerabilities = await scanner.scan_python_file("test.py", "print('test')")
            
            # Should return empty list on timeout, not raise exception
            assert vulnerabilities == []
    
    @pytest.mark.asyncio
    async def test_scan_python_handles_invalid_json(self, scanner):
        """Test that Python scanning handles invalid JSON output."""
        mock_result = Mock()
        mock_result.stdout = "invalid json {{{}"
        
        with patch('subprocess.run', return_value=mock_result):
            vulnerabilities = await scanner.scan_python_file("test.py", "print('test')")
            
            # Should return empty list on parse error
            assert vulnerabilities == []
    
    @pytest.mark.asyncio
    async def test_scan_javascript_file_with_semgrep(self, scanner):
        """Test JavaScript scanning with Semgrep (if available)."""
        if not scanner.semgrep_available:
            pytest.skip("Semgrep not installed")
        
        vulnerable_code = """
const userInput = req.body.data;
element.innerHTML = userInput;  // XSS vulnerability

eval(userInput);  // Code injection
"""
        
        vulnerabilities = await scanner.scan_javascript_file("app.js", vulnerable_code)
        
        # Should detect potential issues
        assert isinstance(vulnerabilities, list)
        
        # Check structure if any found
        for vuln in vulnerabilities:
            assert "type" in vuln
            assert "severity" in vuln
            assert "description" in vuln
    
    @pytest.mark.asyncio
    async def test_scan_javascript_clean_code(self, scanner):
        """Test JavaScript scanning with clean code."""
        if not scanner.semgrep_available:
            pytest.skip("Semgrep not installed")
        
        clean_code = """
import React from 'react';

const App = () => {
  return <div>Hello World</div>;
};

export default App;
"""
        
        vulnerabilities = await scanner.scan_javascript_file("App.jsx", clean_code)
        
        assert isinstance(vulnerabilities, list)
    
    @pytest.mark.asyncio
    async def test_scan_typescript_file(self, scanner):
        """Test TypeScript file scanning."""
        if not scanner.semgrep_available:
            pytest.skip("Semgrep not installed")
        
        ts_code = """
interface User {
  name: string;
  email: string;
}

const getUser = (id: number): User => {
  return { name: "Test", email: "test@example.com" };
};
"""
        
        vulnerabilities = await scanner.scan_javascript_file("user.ts", ts_code)
        
        assert isinstance(vulnerabilities, list)
    
    @pytest.mark.asyncio
    async def test_scan_package_dependencies(self, scanner):
        """Test npm dependency scanning."""
        if not scanner.npm_available:
            pytest.skip("npm not installed")
        
        # Package.json with known old vulnerable versions
        package_json = json.dumps({
            "name": "test-app",
            "version": "1.0.0",
            "dependencies": {
                "express": "4.0.0"  # Old version likely has vulnerabilities
            }
        })
        
        vulnerabilities = await scanner.scan_package_dependencies(package_json)
        
        # Structure check
        assert isinstance(vulnerabilities, list)
        for vuln in vulnerabilities:
            if vuln:  # If any found
                assert "type" in vuln
                assert "severity" in vuln
                assert "description" in vuln
    
    @pytest.mark.asyncio
    async def test_scan_package_dependencies_clean(self, scanner):
        """Test npm scanning with minimal/no dependencies."""
        if not scanner.npm_available:
            pytest.skip("npm not installed")
        
        package_json = json.dumps({
            "name": "test-app",
            "version": "1.0.0",
            "dependencies": {}
        })
        
        vulnerabilities = await scanner.scan_package_dependencies(package_json)
        
        assert isinstance(vulnerabilities, list)
    
    @pytest.mark.asyncio
    async def test_scan_package_handles_timeout(self, scanner):
        """Test npm scanning handles timeout gracefully."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('npm', 60)):
            vulnerabilities = await scanner.scan_package_dependencies('{"dependencies": {}}')
            
            assert vulnerabilities == []
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_hardcoded_secrets(self, scanner):
        """Test pattern scanning detects hardcoded secrets."""
        code_with_secrets = """
API_KEY = "sk_live_1234567890abcdefghijklmnop"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
password = "mysecretpassword"
SECRET_KEY = "django-secret-key-12345"
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("config.py", code_with_secrets)
        
        # Should detect multiple secret patterns
        assert len(vulnerabilities) > 0
        
        # Check for severity levels
        severities = [v["severity"] for v in vulnerabilities]
        assert "CRITICAL" in severities or "HIGH" in severities or "MEDIUM" in severities
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_code_injection(self, scanner):
        """Test pattern scanning detects code injection risks."""
        vulnerable_code = """
user_input = input("Enter code: ")
eval(user_input)
exec(user_input)
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("dangerous.py", vulnerable_code)
        
        # Should detect eval and exec
        assert len(vulnerabilities) >= 2
        
        types = [v["type"] for v in vulnerabilities]
        assert "Code Injection" in types
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_command_injection(self, scanner):
        """Test pattern scanning detects command injection risks."""
        vulnerable_code = """
import os
import subprocess

os.system(user_command)
subprocess.run(cmd, shell=True)
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("runner.py", vulnerable_code)
        
        # Should detect os.system and shell=True
        assert len(vulnerabilities) >= 2
        
        descriptions = [v["description"].lower() for v in vulnerabilities]
        assert any("system" in d or "shell" in d for d in descriptions)
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_xss_risk(self, scanner):
        """Test pattern scanning detects XSS risks."""
        vulnerable_code = """
const App = () => {
  return <div dangerouslySetInnerHTML={{__html: userContent}} />;
};
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("App.jsx", vulnerable_code)
        
        # Should detect dangerouslySetInnerHTML
        assert len(vulnerabilities) > 0
        assert any("xss" in v["type"].lower() for v in vulnerabilities)
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_aws_keys(self, scanner):
        """Test pattern scanning detects AWS access keys."""
        code_with_aws = """
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("config.py", code_with_aws)
        
        # Should detect AWS key pattern
        assert len(vulnerabilities) > 0
        assert any("aws" in v["type"].lower() for v in vulnerabilities)
        assert any(v["severity"] == "CRITICAL" for v in vulnerabilities)
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_stripe_keys(self, scanner):
        """Test pattern scanning detects Stripe secret keys."""
        code_with_stripe = """
STRIPE_SECRET = "sk_live_1234567890abcdefghijklmn"
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("payment.py", code_with_stripe)
        
        # Should detect Stripe key pattern
        assert len(vulnerabilities) > 0
        assert any("stripe" in v["type"].lower() for v in vulnerabilities)
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_scan_clean_code(self, scanner):
        """Test pattern scanning with clean code."""
        clean_code = """
def calculate_total(items):
    return sum(item.price for item in items)

class UserService:
    def get_user(self, user_id):
        return self.db.query(User).filter_by(id=user_id).first()
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("service.py", clean_code)
        
        # Should have minimal or no issues
        assert isinstance(vulnerabilities, list)
    
    @pytest.mark.asyncio
    async def test_fallback_pattern_case_insensitive(self, scanner):
        """Test that pattern scanning is case-insensitive."""
        code_variations = """
EVAL(code)
Exec(code)
API_KEY = "test"
api_key = "test"
"""
        
        vulnerabilities = await scanner.fallback_pattern_scan("test.py", code_variations)
        
        # Should detect patterns regardless of case
        assert len(vulnerabilities) > 0
    
    def test_map_bandit_severity(self, scanner):
        """Test Bandit severity mapping."""
        assert scanner._map_bandit_severity("LOW") == "LOW"
        assert scanner._map_bandit_severity("MEDIUM") == "MEDIUM"
        assert scanner._map_bandit_severity("HIGH") == "HIGH"
        assert scanner._map_bandit_severity("unknown") == "MEDIUM"  # Default
    
    def test_map_semgrep_severity(self, scanner):
        """Test Semgrep severity mapping."""
        assert scanner._map_semgrep_severity("INFO") == "LOW"
        assert scanner._map_semgrep_severity("WARNING") == "MEDIUM"
        assert scanner._map_semgrep_severity("ERROR") == "HIGH"
        assert scanner._map_semgrep_severity("unknown") == "MEDIUM"  # Default
    
    def test_get_bandit_fix_suggestions(self, scanner):
        """Test that Bandit fix suggestions are comprehensive."""
        # Test a few common Bandit test IDs
        assert "pickle" in scanner._get_bandit_fix(test_id="B301").lower()
        assert "md5" in scanner._get_bandit_fix(test_id="B303").lower() or "sha1" in scanner._get_bandit_fix(test_id="B303").lower()
        assert "shell" in scanner._get_bandit_fix(test_id="B601").lower()
        
        # Unknown test ID should return generic message
        fix = scanner._get_bandit_fix(test_id="B999")
        assert "review" in fix.lower() or "fix" in fix.lower()


class TestSecurityScannerIntegration:
    """Integration tests for real-world scanning scenarios."""
    
    @pytest.fixture
    def scanner(self):
        """Create scanner instance."""
        import sys
        import importlib.util
        
        spec = importlib.util.spec_from_file_location(
            "scanner_int",
            "/mnt/user-data/uploads/security_scanner.py"
        )
        scanner_module = importlib.util.module_from_spec(spec)
        sys.modules['scanner_int'] = scanner_module
        spec.loader.exec_module(scanner_module)
        
        return scanner_module.SecurityScanner()
    
    @pytest.mark.asyncio
    async def test_realistic_flask_app_scan(self, scanner):
        """Test scanning a realistic Flask application."""
        flask_code = """
from flask import Flask, request, render_template_string
import sqlite3

app = Flask(__name__)

@app.route('/search')
def search():
    query = request.args.get('q')
    # SQL Injection vulnerability
    conn = sqlite3.connect('db.sqlite')
    results = conn.execute(f"SELECT * FROM users WHERE name = '{query}'")
    return str(results.fetchall())

@app.route('/render')
def render():
    template = request.args.get('template')
    # SSTI vulnerability
    return render_template_string(template)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
"""
        
        # Scan with available tool or fallback
        if scanner.bandit_available:
            vulnerabilities = await scanner.scan_python_file("app.py", flask_code)
        else:
            vulnerabilities = await scanner.fallback_pattern_scan("app.py", flask_code)
        
        # Should detect multiple issues
        assert len(vulnerabilities) > 0
    
    @pytest.mark.asyncio
    async def test_realistic_react_app_scan(self, scanner):
        """Test scanning a realistic React application."""
        react_code = """
import React, { useState } from 'react';

const UserProfile = () => {
  const [bio, setBio] = useState('');
  
  return (
    <div>
      <input onChange={(e) => setBio(e.target.value)} />
      {/* XSS vulnerability */}
      <div dangerouslySetInnerHTML={{__html: bio}} />
      
      {/* Eval usage */}
      <button onClick={() => eval(userCode)}>Run Code</button>
    </div>
  );
};
"""
        
        # Scan with available tool or fallback
        if scanner.semgrep_available:
            vulnerabilities = await scanner.scan_javascript_file("UserProfile.jsx", react_code)
        else:
            vulnerabilities = await scanner.fallback_pattern_scan("UserProfile.jsx", react_code)
        
        # Should detect XSS and eval issues
        assert len(vulnerabilities) > 0


class TestGetScanner:
    """Test the singleton scanner getter."""
    
    def test_get_scanner_returns_instance(self):
        """Test that get_scanner returns a SecurityScanner instance."""
        import sys
        import importlib.util
        
        spec = importlib.util.spec_from_file_location(
            "scanner_singleton",
            "/mnt/user-data/uploads/security_scanner.py"
        )
        scanner_module = importlib.util.module_from_spec(spec)
        sys.modules['scanner_singleton'] = scanner_module
        spec.loader.exec_module(scanner_module)
        
        scanner1 = scanner_module.get_scanner()
        scanner2 = scanner_module.get_scanner()
        
        # Should return the same instance (singleton)
        assert scanner1 is scanner2
        assert isinstance(scanner1, scanner_module.SecurityScanner)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])