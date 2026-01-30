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
You are an expert debugger. Analyze these execution logs and identify issues.

Project Type: {blueprint.get('projectType', 'unknown')}
Tech Stack: {blueprint.get('tech_stack', 'unknown')}

Execution Logs:
{logs[:3000]}

Analyze and output JSON:
{{
  "status": "pass|fail",
  "issues": [
    "Description of issue 1",
    "Description of issue 2"
  ],
  "suggestions": [
    "How to fix issue 1",
    "How to fix issue 2"
  ],
  "fixes": [
    {{
      "file": "filename.ext",
      "change": "Description of the change needed"
    }}
  ]
}}

Focus on:
- Runtime errors
- Missing dependencies
- Syntax errors
- Configuration issues
- Port binding issues

If logs show successful execution, return status: "pass" with empty issues.
Return ONLY the JSON object.
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
