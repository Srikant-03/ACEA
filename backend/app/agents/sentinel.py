# ACEA Sentinel - The Sentinel Agent (OPTIMIZED)
# Security scanning with BATCH processing to reduce API calls

import json
from app.core.config import settings

class SentinelAgent:
    def __init__(self):
        pass

    async def audit_code(self, file_path: str, code: str) -> dict:
        """
        Quick security scan - no API call needed for basic checks.
        Only flags obvious issues.
        """
        vulnerabilities = []
        
        # Basic pattern-based security checks (no API needed)
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
            if pattern.lower() in code.lower():
                vulnerabilities.append({
                    "type": vuln_type,
                    "severity": severity,
                    "description": f"Found '{pattern}' in {file_path}",
                    "fix_suggestion": fix
                })
        
        # Determine status
        has_critical = any(v["severity"] in ["HIGH", "CRITICAL"] for v in vulnerabilities)
        status = "BLOCKED" if has_critical else "APPROVED"
        
        return {
            "status": status,
            "vulnerabilities": vulnerabilities
        }

    async def batch_audit(self, files: dict) -> dict:
        """
        OPTIMIZATION: Audit ALL files in one pass without API calls.
        This reduces API usage from 7+ calls to 0 calls.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": f"Scanning {len(files)} files for security issues..."})
        
        all_vulnerabilities = []
        
        for path, content in files.items():
            result = await self.audit_code(path, content)
            if result["vulnerabilities"]:
                all_vulnerabilities.extend(result["vulnerabilities"])
        
        # Determine overall status
        has_critical = any(v["severity"] in ["HIGH", "CRITICAL"] for v in all_vulnerabilities)
        status = "BLOCKED" if has_critical else "APPROVED"
        
        if all_vulnerabilities:
            await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": f"⚠️ Found {len(all_vulnerabilities)} potential issues"})
        else:
            await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": "✅ No security issues detected"})
        
        return {
            "status": status,
            "vulnerabilities": all_vulnerabilities,
            "files_scanned": len(files)
        }
