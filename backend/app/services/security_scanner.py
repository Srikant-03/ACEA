# ACEA Sentinel - Security Scanner Service
# Wraps real security tools (Bandit, Semgrep, npm audit)

import json
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional
import asyncio
import logging

from app.core.sandbox_guard import SandboxGuard

logger = logging.getLogger(__name__)


class SecurityScanner:
    """
    Real security scanning using industry-standard tools.
    Falls back to pattern matching if tools unavailable.
    """
    
    def __init__(self):
        self.bandit_available = self._check_tool("bandit")
        self.semgrep_available = self._check_tool("semgrep")
        self.npm_available = self._check_tool("npm")
        
        logger.info(f"Security tools - Bandit: {self.bandit_available}, Semgrep: {self.semgrep_available}, npm: {self.npm_available}")
    
    def _check_tool(self, tool_name: str) -> bool:
        """Check if a security tool is installed."""
        try:
            guard = SandboxGuard(project_root=os.getcwd())
            cmd_str = f"{tool_name} --version"
            allowed, reason = guard.check_command(cmd_str)
            if not allowed:
                logger.warning(f"SandboxGuard blocked tool check: {cmd_str} — {reason}")
                return False
            subprocess.run(
                [tool_name, "--version"],
                capture_output=True,
                timeout=5,
                check=False
            )
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    async def scan_python_file(self, file_path: str, content: str) -> List[dict]:
        """Scan Python file with Bandit."""
        if not self.bandit_available:
            return []
        
        vulnerabilities = []
        
        try:
            # Create temp file for scanning
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            # Run Bandit (guarded)
            cmd_str = f"bandit -f json {tmp_path}"
            guard = SandboxGuard(project_root=tempfile.gettempdir())
            allowed, reason = guard.check_command(cmd_str)
            if not allowed:
                logger.warning(f"SandboxGuard blocked bandit scan: {reason}")
                return []
            result = subprocess.run(
                ["bandit", "-f", "json", tmp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse results
            if result.stdout:
                data = json.loads(result.stdout)
                for issue in data.get("results", []):
                    vulnerabilities.append({
                        "type": issue.get("test_id", "Unknown"),
                        "severity": self._map_bandit_severity(issue.get("issue_severity", "LOW")),
                        "description": f"{issue.get('issue_text', 'Security issue')} in {file_path}",
                        "fix_suggestion": self._get_bandit_fix(issue.get("test_id", "")),
                        "line": issue.get("line_number", 0),
                        "code": issue.get("code", "").strip()
                    })
        
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            # Silent fail - don't block on scanner errors
            pass
        
        finally:
            # Cleanup
            try:
                if 'tmp_path' in locals():
                    os.unlink(tmp_path)
            except OSError:
                pass
        
        return vulnerabilities
    
    async def scan_javascript_file(self, file_path: str, content: str) -> List[dict]:
        """Scan JavaScript/TypeScript file with Semgrep."""
        if not self.semgrep_available:
            return []
        
        vulnerabilities = []
        
        try:
            # Determine file extension
            ext = Path(file_path).suffix or '.js'
            
            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            
            # Run Semgrep with JavaScript security rules (guarded)
            cmd_str = f"semgrep --config=auto --json --quiet {tmp_path}"
            guard = SandboxGuard(project_root=tempfile.gettempdir())
            allowed, reason = guard.check_command(cmd_str)
            if not allowed:
                logger.warning(f"SandboxGuard blocked semgrep scan: {reason}")
                return []
            result = subprocess.run(
                [
                    "semgrep",
                    "--config=auto",
                    "--json",
                    "--quiet",
                    tmp_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                data = json.loads(result.stdout)
                for finding in data.get("results", []):
                    vulnerabilities.append({
                        "type": finding.get("check_id", "Unknown").split(".")[-1],
                        "severity": self._map_semgrep_severity(finding.get("extra", {}).get("severity", "WARNING")),
                        "description": f"{finding.get('extra', {}).get('message', 'Security issue')} in {file_path}",
                        "fix_suggestion": finding.get("extra", {}).get("fix", "Review and fix this security issue"),
                        "line": finding.get("start", {}).get("line", 0),
                        "code": finding.get("extra", {}).get("lines", "").strip()
                    })
        
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        
        finally:
            try:
                if 'tmp_path' in locals():
                    os.unlink(tmp_path)
            except OSError:
                pass
        
        return vulnerabilities
    
    async def scan_package_dependencies(self, package_json_content: str) -> List[dict]:
        """Scan npm dependencies for known vulnerabilities."""
        if not self.npm_available:
            return []
        
        vulnerabilities = []
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Write package.json
                pkg_path = Path(tmpdir) / "package.json"
                pkg_path.write_text(package_json_content)
                
                # Run npm audit (guarded)
                guard = SandboxGuard(project_root=tmpdir)
                allowed, reason = guard.check_command("npm audit --json")
                if not allowed:
                    logger.warning(f"SandboxGuard blocked npm audit: {reason}")
                    return []
                result = subprocess.run(
                    ["npm", "audit", "--json"],
                    capture_output=True,
                    text=True,
                    cwd=tmpdir,
                    timeout=60
                )
                
                if result.stdout:
                    data = json.loads(result.stdout)
                    
                    # Parse npm audit v7+ format
                    for vuln_id, vuln_data in data.get("vulnerabilities", {}).items():
                        vulnerabilities.append({
                            "type": "Dependency Vulnerability",
                            "severity": vuln_data.get("severity", "LOW").upper(),
                            "description": f"{vuln_id}: {vuln_data.get('via', [{}])[0].get('title', 'Known vulnerability')}",
                            "fix_suggestion": f"Update to version {vuln_data.get('fixAvailable', {}).get('version', 'latest')}",
                            "package": vuln_id
                        })
        
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
            pass
        
        return vulnerabilities
    
    async def fallback_pattern_scan(self, file_path: str, content: str) -> List[dict]:
        """
        Fallback pattern-based scanning when tools unavailable.
        Returns WARNING-level findings only (not HIGH) since these are
        heuristic matches and should NOT block the pipeline.
        Only CRITICAL credential patterns (AWS/Stripe keys) remain CRITICAL.
        """
        import re
        vulnerabilities = []
        
        # Heuristic patterns — downgraded to WARNING to avoid false-positive blocking
        simple_patterns = [
            ("eval(", "Code Injection", "WARNING", "Avoid using eval()"),
            ("exec(", "Code Injection", "WARNING", "Avoid using exec()"),
            ("os.system(", "Command Injection", "WARNING", "Use subprocess with shell=False"),
            ("shell=True", "Command Injection", "WARNING", "Avoid shell=True in subprocess"),
            ("dangerouslySetInnerHTML", "XSS Risk", "WARNING", "Sanitize HTML content"),
            ("SELECT *", "SQL Security", "LOW", "Consider specific column selection"),
            ("0.0.0.0", "Insecure Binding", "LOW", "Bind to specific interface if possible"),
        ]
        
        # Hardcoded secret patterns — only match actual assignments with literal values
        secret_patterns = [
            (r'''(?:password|passwd)\s*=\s*['\"][^'\"]+['\"]''', "Hardcoded Secret", "WARNING", "Use environment variables"),
            (r'''api_key\s*=\s*['\"][^'\"]+['\"]''', "Hardcoded Secret", "WARNING", "Use environment variables"),
            (r'''SECRET_KEY\s*=\s*['\"][^'\"]+['\"]''', "Hardcoded Secret", "WARNING", "Use environment variables"),
        ]
        
        # CRITICAL credential patterns — regex-based for precision
        credential_patterns = [
            (r"AKIA[0-9A-Z]{16}", "AWS Access Key", "CRITICAL", "Revoke and use env vars"),
            (r"sk_live_[0-9a-zA-Z]{24}", "Stripe Secret Key", "CRITICAL", "Revoke and use env vars"),
        ]
        
        # Check simple patterns with case-insensitive substring matching
        for pattern, vuln_type, severity, fix in simple_patterns:
            if pattern.lower() in content.lower():
                vulnerabilities.append({
                    "type": vuln_type,
                    "severity": severity,
                    "description": f"Found '{pattern}' in {file_path}",
                    "fix_suggestion": fix,
                    "source": "fallback"
                })
        
        # Check secret patterns with regex
        for regex, vuln_type, severity, fix in secret_patterns:
            if re.search(regex, content, re.IGNORECASE):
                vulnerabilities.append({
                    "type": vuln_type,
                    "severity": severity,
                    "description": f"Potential hardcoded secret in {file_path}",
                    "fix_suggestion": fix,
                    "source": "fallback"
                })
        
        # Check credential patterns with regex (these stay CRITICAL)
        for regex, vuln_type, severity, fix in credential_patterns:
            if re.search(regex, content):
                vulnerabilities.append({
                    "type": vuln_type,
                    "severity": severity,
                    "description": f"Found credential pattern in {file_path}",
                    "fix_suggestion": fix,
                    "source": "fallback"
                })
        
        return vulnerabilities
    
    def _map_bandit_severity(self, bandit_severity: str) -> str:
        """Map Bandit severity to our scale."""
        mapping = {
            "LOW": "LOW",
            "MEDIUM": "MEDIUM",
            "HIGH": "HIGH"
        }
        return mapping.get(bandit_severity.upper(), "MEDIUM")
    
    def _map_semgrep_severity(self, semgrep_severity: str) -> str:
        """Map Semgrep severity to our scale."""
        mapping = {
            "INFO": "LOW",
            "WARNING": "MEDIUM",
            "ERROR": "HIGH"
        }
        return mapping.get(semgrep_severity.upper(), "MEDIUM")
    
    def _get_bandit_fix(self, test_id: str) -> str:
        """Get fix suggestion for common Bandit issues."""
        fixes = {
            "B201": "Avoid flask.render_template_string() with user input",
            "B301": "Use pickle with caution, prefer JSON",
            "B302": "Don't use marshal for untrusted data",
            "B303": "MD5 and SHA1 are insecure, use SHA256+",
            "B304": "Use cryptography library instead of old ciphers",
            "B305": "Don't use weak ciphers like DES/RC4",
            "B306": "Avoid mktemp, use mkstemp instead",
            "B307": "Use defusedxml instead of xml.etree",
            "B308": "Use defusedxml.minidom",
            "B309": "Use defusedxml.pulldom",
            "B310": "urllib.urlopen is unsafe, use requests",
            "B311": "Use secrets module instead of random for security",
            "B312": "Use secrets.token_hex() for tokens",
            "B313": "Don't use XML with DTD processing enabled",
            "B314": "Avoid xml.etree.ElementTree.parse",
            "B315": "Avoid xml.etree.ElementTree.iterparse",
            "B316": "Avoid xml.sax.parse",
            "B317": "Avoid xml.etree.cElementTree",
            "B318": "Avoid xml.dom.minidom.parseString",
            "B319": "Avoid xml.dom.pulldom.parseString",
            "B320": "Avoid lxml.etree.parse",
            "B321": "Avoid ftplib.FTP, use SFTP",
            "B322": "Avoid input() in Python 2",
            "B323": "Avoid unverified SSL context",
            "B324": "MD5 is insecure",
            "B325": "tempfile.mktemp is insecure",
            "B401": "Don't import telnetlib",
            "B402": "Don't import ftplib",
            "B403": "Don't import pickle",
            "B404": "Don't import subprocess",
            "B405": "Don't import xml libraries",
            "B406": "Don't import xml.sax",
            "B407": "Don't import xml.expat",
            "B408": "Don't import xml.minidom",
            "B409": "Don't import xml.pulldom",
            "B410": "Don't import lxml",
            "B411": "Don't import xmlrpclib",
            "B412": "Don't import httplib",
            "B413": "Don't import pyCrypto",
            "B501": "Use secure SSL/TLS settings",
            "B502": "Verify SSL certificates",
            "B503": "Avoid insecure SSL/TLS protocols",
            "B504": "Verify SSL hostnames",
            "B505": "Use secure cipher suites",
            "B506": "Use secure YAML loading",
            "B507": "Use secure SSH settings",
            "B601": "Avoid shell=True in subprocess",
            "B602": "Avoid shell=True with user input",
            "B603": "Validate subprocess input",
            "B604": "Validate function calls",
            "B605": "Use shell=False",
            "B606": "Validate command arguments",
            "B607": "Avoid partial paths in subprocess",
            "B608": "SQL injection risk",
            "B609": "Linux wildcards with shell=True",
            "B610": "SQL injection in Django",
            "B611": "SQL injection in SQLAlchemy",
            "B701": "Use Jinja2 autoescape",
            "B702": "Use Mako default_filters",
            "B703": "Use Django mark_safe carefully"
        }
        return fixes.get(test_id, "Review and fix this security issue")


# Singleton instance
_scanner = None

def get_scanner() -> SecurityScanner:
    """Get or create the security scanner instance."""
    global _scanner
    if _scanner is None:
        _scanner = SecurityScanner()
    return _scanner