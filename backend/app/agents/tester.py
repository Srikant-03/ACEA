# ACEA Sentinel - Tester Agent
# Analyzes execution logs and suggests fixes

import json
from typing import Dict, List, Optional


class TesterAgent:
    """Analyzes execution logs and provides debugging assistance."""
    
    def __init__(self):
        pass
    
    async def analyze_execution(self, logs: str, blueprint: dict) -> Dict:
        """
        Analyze execution logs and identify issues.
        
        Returns:
        {
            "status": "pass|fail",
            "issues": List[str],
            "suggestions": List[str],
            "fixes": List[dict]
        }
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "TESTER", "message": "Analyzing execution logs..."})
        
        prompt = f"""
You are an expert software debugger. Analyze the execution logs and identify the root cause of the failure.

**PROJECT CONTEXT**:
- Project Type: {blueprint.get('projectType', 'unknown')}
- Tech Stack: {blueprint.get('tech_stack', 'unknown')}

**EXECUTION LOGS**:
{logs[:5000]}

**TASK**:
1. Identify the specific file(s) causing the error.
2. Provide a concrete fix instruction for each file.
3. Classify the error type (Syntax, Runtime, Configuration, Missing Dependency).

**OUTPUT FORMAT**:
Return valid JSON only. No markdown.
{{
  "status": "fail",
  "issues": [
    "Brief description of issue 1",
    "Brief description of issue 2"
  ],
  "fixes": [
    {{
      "file": "path/to/file.ext",
      "change": "Detailed instruction on how to fix the code. Be specific about what to change."
    }},
    {{
      "file": "frontend/package.json",
      "change": "Add 'dependency-name': '^1.0.0' to dependencies"
    }}
  ]
}}

**RULES**:
- If a file is missing, suggest creating it.
- If a dependency is missing, strict "package.json" as the file to fix.
- If the error is obscure, look for "Caused by" or "Stack trace" lines.
- If logs show keys/secrets missing, suggest adding to .env.
- If logs show successful execution (server running, listening on port), return status: "pass".
"""
        
        try:
            response = await client.generate(prompt, json_mode=True)
            result = json.loads(response)
            
            status = result.get("status", "unknown")
            issues = result.get("issues", [])
            
            if status == "fail" and issues:
                await sm.emit("agent_log", {"agent_name": "TESTER", "message": f"❌ Found {len(issues)} issues"})
            else:
                await sm.emit("agent_log", {"agent_name": "TESTER", "message": "✅ Execution looks healthy"})
            
            return result
            
        except Exception as e:
            await sm.emit("agent_log", {"agent_name": "TESTER", "message": f"⚠️ Analysis error: {str(e)[:50]}"})
            return {
                "status": "error",
                "issues": [f"Analysis failed: {str(e)}"],
                "suggestions": ["Check logs manually"],
                "fixes": []
            }
    
    def quick_check(self, logs: str) -> Dict:
        """
        Quick pattern-based log analysis (no API call).
        """
        issues = []
        suggestions = []
        
        # Common error patterns
        patterns = {
            "ModuleNotFoundError": ("Missing Python module", "Run: pip install <module>"),
            "Cannot find module": ("Missing Node module", "Run: npm install"),
            "SyntaxError": ("Syntax error in code", "Check the indicated file and line"),
            "EADDRINUSE": ("Port already in use", "Stop other services or change port"),
            "ENOENT": ("File not found", "Check file paths"),
            "EACCES": ("Permission denied", "Check file permissions"),
            "npm ERR!": ("NPM error", "Check package.json and run npm install"),
            "pip.*error": ("Pip installation error", "Check requirements.txt"),
        }
        
        logs_lower = logs.lower()
        
        for pattern, (issue, suggestion) in patterns.items():
            if pattern.lower() in logs_lower:
                issues.append(issue)
                suggestions.append(suggestion)
        
        return {
            "status": "fail" if issues else "pass",
            "issues": issues,
            "suggestions": suggestions,
            "fixes": []
        }
