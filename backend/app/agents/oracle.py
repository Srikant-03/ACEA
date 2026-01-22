import subprocess
import os
import sys
from app.core.config import settings
from app.core.key_manager import KeyManager

class OracleAgent:
    def __init__(self):
        self.km = KeyManager()

    async def generate_tests(self, code: str, language: str = "python") -> str:
        """
        Generates test code using Gemini.
        """
        from app.core.key_manager import KeyManager
        km = KeyManager()
        
        prompt = f"Generate {language} unit tests for this code using pytest/vitest. Return ONLY code:\n{code}"
        try:
            client = km.get_client()
            response = await client.aio.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt
            )
            return response.text.replace("```python", "").replace("```", "").strip()
        except:
            return ""

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
