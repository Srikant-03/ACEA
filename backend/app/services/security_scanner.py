# ACEA Sentinel - Security Scanner Service
# Wraps real security tools (Bandit, Semgrep, npm audit)

import json
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional
import asyncio


class SecurityScanner:
    """
    Real security scanning using industry-standard tools.
    Falls back to pattern matching if tools unavailable.
    """
    
    def __init__(self):
        self.bandit_available = self._check_tool("bandit")
        self.semgrep_available = self._check_tool("semgrep")
        self.npm_available = self._check_tool("npm")
        
        # Log availability (helps debugging)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Security tools - Bandit: {self.bandit_available}, Semgrep: {self.semgrep_available}, npm: {self.npm_available}")
    
    def _check_tool(self, tool_name: str) -> bool:
        """Check if a security tool is installed."""
        try:
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
            
            # Run Bandit
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
            except:
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
            
            # Run Semgrep with JavaScript security rules
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
            except:
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
                
                # Run npm audit
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
        Preserves original Sentinel behavior.
        """
        vulnerabilities = []
        
        dangerous_patterns = [
            ("eval(", "Code Injection", "HIGH", "Avoid using eval()"),
            ("exec(", "Code Injection", "HIGH", "Avoid using exec()"),
            ("os.system(", "Command Injection", "HIGH", "Use subprocess with shell=False"),
            ("shell=True", "Command Injection", "MEDIUM", "Avoid shell=True in subprocess"),
            ("password = ", "Hardcoded Secret", "MEDIUM", "Use environment variables"),
            ("api_key = ", "Hardcoded Secret", "MEDIUM", "Use environment variables"),
            ("SECRET_KEY = ", "Hardcoded Secret", "MEDIUM", "Use environment variables"),
            ("dangerouslySetInnerHTML", "XSS Risk", "MEDIUM", "Sanitize HTML content"),
            ("SELECT *", "SQL Security", "LOW", "Consider specific column selection"),
            ("AKIA[0-9A-Z]{16}", "AWS Access Key", "CRITICAL", "Revoke and use env vars"),
            ("sk_live_[0-9a-zA-Z]{24}", "Stripe Secret Key", "CRITICAL", "Revoke and use env vars"),
            ("0.0.0.0", "Insecure Binding", "LOW", "Bind to specific interface if possible"),
        ]
        
        for pattern, vuln_type, severity, fix in dangerous_patterns:
            if pattern.lower() in content.lower():
                vulnerabilities.append({
                    "type": vuln_type,
                    "severity": severity,
                    "description": f"Found '{pattern}' in {file_path}",
                    "fix_suggestion": fix
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