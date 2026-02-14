# app/agents/sentinel_agent.py
import subprocess
import json
from app.agents.state import AgentState, Issue

class SentinelAgent:
    async def run(self, state: AgentState) -> AgentState:
        """
        Run security scans on the generated project.
        Update state.issues with any found vulnerabilities.
        """
        # Ensure project_id is available; use it to derive project_dir
        # state.project_id was added in Dev 1
        # But Dev 2 prompt says: "project_dir = state.project_dir # Directory of code to scan (set by Orchestrator)"
        # I should check if state has project_dir, or derive it.
        
        project_dir = getattr(state, "project_dir", None)
        if not project_dir:
             # Try to derive from project_id if standardized
             if getattr(state, "project_id", None):
                 # Assuming standard path structure or use current dir?
                 # Dev 2 prompt example shows direct access. 
                 # I will safely get it or default to "."
                 project_dir = "." 
        
        state.messages.append("SentinelAgent: Running security scans.")
        
        # 1. Run Bandit (Python security)
        try:
            # Check if bandit is installed first? "Error Handling ... catch the exception"
            result = subprocess.run(
                ["bandit", "-r", project_dir, "-f", "json"],
                capture_output=True, text=True
            )
            # Bandit returns non-zero exit code if issues found, so we don't use check=True
            # But prompt used check=True in try block.
            # I will use check=False to capture output even on failure.
            
            if result.stdout.strip():
                try:
                    bandit_data = json.loads(result.stdout)
                    for vuln in bandit_data.get("results", []):
                        state.issues.append(Issue(
                            file=vuln.get("filename"), 
                            issue=vuln.get("issue_text"), 
                            fix=vuln.get("test_id")
                        ))
                except json.JSONDecodeError:
                    state.messages.append(f"SentinelAgent: Bandit returned invalid JSON")
        except Exception as e:
            state.messages.append(f"SentinelAgent: Bandit scan failed: {e}")

        # 2. Run Semgrep (Python and JS)
        try:
            result = subprocess.run(
                ["semgrep", "scan", "--config=auto", project_dir, "--json"],
                capture_output=True, text=True
            )
            # Semgrep also returns non-zero on findings
            
            if result.stdout.strip():
                try: 
                    semgrep_data = json.loads(result.stdout)
                    for finding in semgrep_data.get("results", []):
                        state.issues.append(Issue(
                            file=finding["path"], 
                            issue=finding["extra"]["message"], 
                            fix=finding["extra"].get("fix", "")
                        ))
                except json.JSONDecodeError:
                     pass
        except Exception as e:
            state.messages.append(f"SentinelAgent: Semgrep scan failed: {e}")

        # 3. Run npm audit (Node/JS)
        # Check if package.json exists first to avoid error spam?
        # User prompt says: "Run npm audit invalid... catch exception... continue"
        try:
            result = subprocess.run(
                ["npm", "audit", "--json"], 
                cwd=project_dir,
                capture_output=True, text=True
            )
            # npm audit returns exit code 1 if vulnerabilities found
            
            if result.stdout.strip():
                try:
                    audit_data = json.loads(result.stdout)
                    for pkg, vuln in audit_data.get("vulnerabilities", {}).items():
                        # npm audit format varies by version (v6 vs v7+).
                        # Assuming standard structure or adapting.
                        # User prompt example: audit_data.get("vulnerabilities", {}).items()
                        # This works for npm 6. npm 7+ has different structure (auditReportVersion 2).
                        # But following user snippet exactly is safer.
                        state.issues.append(Issue(
                            file=pkg, 
                            issue=vuln.get("title", "NPM vulnerability") if isinstance(vuln, dict) else "Vulnerability", 
                            fix=vuln.get("recommendation", "") if isinstance(vuln, dict) else ""
                        ))
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            state.messages.append(f"SentinelAgent: npm audit failed: {e}")

        state.messages.append(f"SentinelAgent: Security scans complete, issues found: {len(state.issues)}.")
        return state
