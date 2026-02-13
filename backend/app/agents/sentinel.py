# ACEA Sentinel - The Sentinel Agent (UPGRADED)
# Security scanning with REAL TOOLS (Bandit, Semgrep, npm audit)
# Falls back to pattern matching if tools unavailable
# OPTIMIZED: BATCH processing, zero API calls

import json
from pathlib import Path
from typing import Dict, List
from app.core.config import settings


class SentinelAgent:
    def __init__(self):
        # Import scanner lazily to avoid circular imports
        self._scanner = None
    
    @property
    def scanner(self):
        """Lazy-load the security scanner."""
        if self._scanner is None:
            from app.services.security_scanner import get_scanner
            self._scanner = get_scanner()
        return self._scanner

    async def audit_code(self, file_path: str, code: str) -> dict:
        """
        Enhanced security scan using real tools.
        Falls back to pattern matching if tools unavailable.
        NO API CALLS - uses local tools only.
        """
        vulnerabilities = []
        
        # Determine file type and use appropriate scanner
        file_ext = Path(file_path).suffix.lower()
        
        # Python files - use Bandit if available
        if file_ext == '.py':
            if self.scanner.bandit_available:
                vulnerabilities.extend(
                    await self.scanner.scan_python_file(file_path, code)
                )
            else:
                # Fallback to pattern matching
                vulnerabilities.extend(
                    await self.scanner.fallback_pattern_scan(file_path, code)
                )
        
        # JavaScript/TypeScript files - use Semgrep if available
        elif file_ext in ['.js', '.jsx', '.ts', '.tsx', '.vue']:
            if self.scanner.semgrep_available:
                vulnerabilities.extend(
                    await self.scanner.scan_javascript_file(file_path, code)
                )
            else:
                # Fallback to pattern matching
                vulnerabilities.extend(
                    await self.scanner.fallback_pattern_scan(file_path, code)
                )
        
        # All other files - pattern matching only
        else:
            vulnerabilities.extend(
                await self.scanner.fallback_pattern_scan(file_path, code)
            )
        
        # Determine status
        has_critical = any(v["severity"] in ["HIGH", "CRITICAL"] for v in vulnerabilities)
        status = "BLOCKED" if has_critical else "APPROVED"
        
        return {
            "status": status,
            "vulnerabilities": vulnerabilities
        }

    async def batch_audit(self, files: dict) -> dict:
        """
        OPTIMIZED: Audit ALL files in one pass with real security tools.
        NO API CALLS - uses local tools (Bandit, Semgrep, npm audit).
        Falls back to pattern matching if tools unavailable.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        # Log scanning start with tool status
        tool_status = []
        if self.scanner.bandit_available:
            tool_status.append("Bandit")
        if self.scanner.semgrep_available:
            tool_status.append("Semgrep")
        if self.scanner.npm_available:
            tool_status.append("npm audit")
        
        if tool_status:
            await sm.emit("agent_log", {
                "agent_name": "SENTINEL",
                "message": f"🔍 Scanning {len(files)} files with {', '.join(tool_status)}..."
            })
        else:
            await sm.emit("agent_log", {
                "agent_name": "SENTINEL",
                "message": f"Scanning {len(files)} files for security issues..."
            })
        
        all_vulnerabilities = []
        
        # Scan all code files
        for path, content in files.items():
            result = await self.audit_code(path, content)
            if result["vulnerabilities"]:
                all_vulnerabilities.extend(result["vulnerabilities"])
        
        # Check package.json dependencies if present
        if "package.json" in files and self.scanner.npm_available:
            await sm.emit("agent_log", {
                "agent_name": "SENTINEL",
                "message": "📦 Auditing npm dependencies..."
            })
            dep_vulns = await self.scanner.scan_package_dependencies(files["package.json"])
            if dep_vulns:
                all_vulnerabilities.extend(dep_vulns)
                await sm.emit("agent_log", {
                    "agent_name": "SENTINEL",
                    "message": f"⚠️ Found {len(dep_vulns)} dependency vulnerabilities"
                })
        
        # Determine overall status
        has_critical = any(v["severity"] in ["HIGH", "CRITICAL"] for v in all_vulnerabilities)
        status = "BLOCKED" if has_critical else "APPROVED"
        
        # Log results with enhanced detail
        if all_vulnerabilities:
            severity_counts = self._count_by_severity(all_vulnerabilities)
            severity_msg = ", ".join([f"{count} {sev}" for sev, count in severity_counts.items()])
            await sm.emit("agent_log", {
                "agent_name": "SENTINEL",
                "message": f"⚠️ Found {len(all_vulnerabilities)} potential issues: {severity_msg}"
            })
            
            # Log critical issues separately
            if has_critical:
                critical_issues = [v for v in all_vulnerabilities if v["severity"] in ["HIGH", "CRITICAL"]]
                await sm.emit("agent_log", {
                    "agent_name": "SENTINEL",
                    "message": f"🚨 CRITICAL: {len(critical_issues)} high-severity issues must be fixed"
                })
        else:
            await sm.emit("agent_log", {
                "agent_name": "SENTINEL",
                "message": "✅ No security issues detected"
            })
        
        return {
            "status": status,
            "vulnerabilities": all_vulnerabilities,
            "files_scanned": len(files)
        }
    
    def _count_by_severity(self, vulnerabilities: List[dict]) -> dict:
        """Count vulnerabilities by severity level."""
        counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for v in vulnerabilities:
            severity = v.get("severity", "LOW")
            if severity in counts:
                counts[severity] += 1
        # Only return non-zero counts
        return {k: v for k, v in counts.items() if v > 0}