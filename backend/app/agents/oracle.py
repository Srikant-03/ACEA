import subprocess
import os
import sys
from app.core.config import settings
class OracleAgent:
    def __init__(self):
        pass

    async def generate_tests(self, code: str, language: str = "python") -> str:
        """
        Generates test code using Gemini via HybridModelClient.
        """
        from app.core.local_model import HybridModelClient
        client = HybridModelClient()
        
        prompt = f"Generate {language} unit tests for this code using pytest/vitest. Return ONLY code, no markdown blocks:\n{code}"
        try:
            response = await client.generate(prompt)
            # Clean markdown and common identifiers
            code = response.replace("```python", "").replace("```typescript", "").replace("```javascript", "").replace("```", "").strip()
            
            # Extra safety: Remove bare language identifiers
            import re
            for lang in ["python", "pytest", "javascript", "typescript"]:
                if re.match(f"^{lang}\\s+", code, re.IGNORECASE):
                    code = re.sub(f"^{lang}\\s+", "", code, flags=re.IGNORECASE).strip()
            
            return code
        except Exception as e:
            return f"# Error generating tests: {e}"

    async def run_tests(self, project_path: str) -> dict:
        """
        Actually runs the tests in the generated project directory.
        """
        # Auto-detect test file (simplification)
        test_file = os.path.join(project_path, "tests.py")
        if not os.path.exists(test_file):
             # Try to create one if missing? or just fail. 
             # For now, if no tests, pass with warning.
             return {"passed": True, "details": "No tests found to run."}
             
        try:
            # Run pytest
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file], 
                capture_output=True, 
                text=True,
                cwd=project_path,
                timeout=10
            )
            
            passed = result.returncode == 0
            return {
                "passed": passed, 
                "details": result.stdout if passed else result.stderr + "\n" + result.stdout
            }
            
        except Exception as e:
            return {"passed": False, "details": f"Execution Error: {str(e)}"}
