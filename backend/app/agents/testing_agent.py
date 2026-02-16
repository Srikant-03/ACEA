# ACEA Sentinel - The Testing Agent
# Generates and executes tests for produced code with multi-framework support

from app.core.config import settings
import json
import asyncio
import subprocess
import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Optional
from app.agents.state import AgentState

class TestingAgent:
    def __init__(self):
        self.supported_frameworks = {
            "python": ["pytest", "unittest"],
            "javascript": ["vitest", "jest", "mocha"],
            "typescript": ["vitest", "jest"]
        }

    async def run(self, state: AgentState) -> AgentState:
        """
        Execute unit and E2E tests. Append failures to state.issues.
        """
        project_dir = getattr(state, "project_dir", ".")
        
        state.messages.append("TestingAgent: Running PyTest...")
        try:
            # Check if pytest is available first?
            # subprocess.run raises FileNotFoundError if command not found
            result = subprocess.run(
                ["pytest", "--maxfail=1", "--disable-warnings", "--json-report"],
                cwd=project_dir, capture_output=True, text=True
            )
            
            if result.returncode != 0:
                # Issue isn't defined in this file, need to make sure Issue is imported
                # state.issues is list of Issue objects
                # Issue(file="PyTest", issue="Unit tests failed", fix="Check logs")
                from app.agents.state import Issue
                state.issues.append(Issue(file="PyTest", issue="Unit tests failed", fix="Check logs"))
                error_msg = f"TestingAgent: PyTest errors: {result.stderr}"
                state.messages.append(error_msg)
                state.errors.append(f"PyTest Failed: {result.stderr[:500]}") # Truncate for safety
        except Exception as e:
            state.messages.append(f"TestingAgent: PyTest invocation failed: {e}")
            state.errors.append(f"PyTest execution error: {str(e)}")

        state.messages.append("TestingAgent: Running Vitest...")
        try:
            result = subprocess.run(
                ["npm", "run", "test:vitest"], cwd=project_dir,
                capture_output=True, text=True
            )
            if result.returncode != 0:
                from app.agents.state import Issue
                state.issues.append(Issue(file="Vitest", issue="Frontend tests failed", fix="Check logs"))
                error_msg = f"TestingAgent: Vitest errors: {result.stderr}"
                state.messages.append(error_msg)
                state.errors.append(f"Vitest Failed: {result.stderr[:500]}")
        except Exception as e:
            from app.agents.state import Issue
            # Optional: don't fail if npm fails (e.g. no frontend)
            state.messages.append(f"TestingAgent: Vitest invocation failed: {e}")
            # Don't add to state.errors if it's just missing npm/tests, logic depends on strictness.
            # safe to ignore unless vital.
            pass

        state.messages.append("TestingAgent: Tests complete.")
        return state

    async def generate_and_run_tests(
        self, 
        project_path: str, 
        file_system: Dict[str, str],
        tech_stack: str = "Auto-detect"
    ) -> dict:
        """
        Main entry point: generates tests for all testable files, then runs them.
        Returns comprehensive test report.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "TESTING", "message": "🧪 Analyzing codebase for testable files..."})
        
        # Step 1: Detect test framework
        framework = await self._detect_framework(project_path, file_system, tech_stack)
        await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"📋 Detected framework: {framework}"})
        
        # Step 2: Generate test files
        test_files = await self._generate_tests(file_system, framework, sm)
        
        if not test_files:
            await sm.emit("agent_log", {"agent_name": "TESTING", "message": "⚠️ No testable files found"})
            return {
                "success": True,
                "framework": framework,
                "tests_generated": 0,
                "tests_run": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "details": "No testable code files detected"
            }
        
        await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"✅ Generated {len(test_files)} test files"})
        
        # Step 3: Write test files to disk
        await self._write_test_files(project_path, test_files, sm)
        
        # Step 4: Run tests
        await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"🚀 Running tests with {framework}..."})
        test_results = await self._run_tests(project_path, framework, sm)
        
        # Step 5: Return comprehensive report
        return test_results

    async def _detect_framework(
        self, 
        project_path: str, 
        file_system: Dict[str, str],
        tech_stack: str
    ) -> str:
        """
        Detects which test framework to use based on project structure and tech stack.
        """
        # Check package.json for JS/TS projects
        package_json_path = os.path.join(project_path, "frontend", "package.json")
        if os.path.exists(package_json_path):
            try:
                with open(package_json_path, 'r') as f:
                    package_data = json.load(f)
                    deps = {**package_data.get("dependencies", {}), **package_data.get("devDependencies", {})}
                    
                    if "vitest" in deps:
                        return "vitest"
                    elif "jest" in deps:
                        return "jest"
                    elif "mocha" in deps:
                        return "mocha"
            except:
                pass
        
        # Check for Python files
        has_python = any(path.endswith(".py") for path in file_system.keys())
        has_js_ts = any(path.endswith((".js", ".jsx", ".ts", ".tsx")) for path in file_system.keys())
        
        if has_python:
            return "pytest"
        elif has_js_ts:
            # Default to vitest for modern projects
            if "vite" in tech_stack.lower() or "next" in tech_stack.lower():
                return "vitest"
            return "jest"
        
        return "pytest"  # Default fallback

    async def _generate_tests(
        self, 
        file_system: Dict[str, str],
        framework: str,
        sm
    ) -> Dict[str, str]:
        """
        Generates test code for all testable files using LLM.
        Returns dict of {test_file_path: test_code}
        """
        from app.core.local_model import HybridModelClient
        
        client = HybridModelClient()
        test_files = {}
        
        # Identify testable files (exclude configs, tests, node_modules)
        testable_files = self._find_testable_files(file_system)
        
        for file_path, file_content in testable_files.items():
            try:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"📝 Generating tests for {file_path}..."})
                
                # Determine language
                language = self._get_language(file_path)
                
                # Generate test file path
                test_file_path = self._get_test_file_path(file_path, framework)
                
                # Create prompt
                prompt = self._create_test_generation_prompt(
                    file_path, 
                    file_content, 
                    framework, 
                    language
                )
                
                # Generate tests
                response = await client.generate(prompt)
                
                # Clean response
                test_code = self._clean_generated_code(response, language)
                
                test_files[test_file_path] = test_code
                
            except Exception as e:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"⚠️ Failed to generate test for {file_path}: {str(e)[:50]}"})
                continue
        
        return test_files

    def _find_testable_files(self, file_system: Dict[str, str]) -> Dict[str, str]:
        """
        Filters file_system to only include files that should have tests.
        Excludes: configs, existing tests, node_modules, build outputs.
        """
        testable = {}
        
        exclude_patterns = [
            r"\.config\.",
            r"\.test\.",
            r"\.spec\.",
            r"__tests__",
            r"node_modules",
            r"dist/",
            r"build/",
            r"\.next/",
            r"venv/",
            r"__pycache__",
            r"package\.json",
            r"tsconfig\.json",
            r"postcss\.config",
            r"tailwind\.config",
            r"next\.config",
            r"vite\.config"
        ]
        
        for path, content in file_system.items():
            # Skip if matches exclude pattern
            if any(re.search(pattern, path) for pattern in exclude_patterns):
                continue
            
            # Include only source code files
            if path.endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
                # Skip if file is too small (likely empty or just imports)
                if len(content.strip()) > 50:
                    testable[path] = content
        
        return testable

    def _get_language(self, file_path: str) -> str:
        """Returns language identifier for the file."""
        if file_path.endswith(".py"):
            return "python"
        elif file_path.endswith((".ts", ".tsx")):
            return "typescript"
        elif file_path.endswith((".js", ".jsx")):
            return "javascript"
        return "unknown"

    def _get_test_file_path(self, source_path: str, framework: str) -> str:
        """
        Generates appropriate test file path based on framework conventions.
        """
        path_obj = Path(source_path)
        
        if framework == "pytest":
            # Python: tests/test_filename.py
            return f"backend/tests/test_{path_obj.stem}.py"
        
        elif framework in ["vitest", "jest"]:
            # JS/TS: place .test.ts next to source or in __tests__
            if "frontend" in source_path:
                # Keep in frontend, add .test before extension
                return source_path.replace(path_obj.suffix, f".test{path_obj.suffix}")
            else:
                return f"frontend/__tests__/{path_obj.stem}.test.ts"
        
        else:
            # Default fallback
            return f"tests/{path_obj.stem}.test{path_obj.suffix}"

    def _create_test_generation_prompt(
        self, 
        file_path: str, 
        file_content: str, 
        framework: str,
        language: str
    ) -> str:
        """Creates optimized prompt for test generation."""
        
        framework_examples = {
            "pytest": """
import pytest
from module import function

def test_function_happy_path():
    result = function(valid_input)
    assert result == expected_output

def test_function_edge_case():
    with pytest.raises(ValueError):
        function(invalid_input)
""",
            "vitest": """
import { describe, it, expect } from 'vitest';
import { function } from './module';

describe('function', () => {
  it('should handle happy path', () => {
    const result = function(validInput);
    expect(result).toBe(expectedOutput);
  });
  
  it('should handle edge case', () => {
    expect(() => function(invalidInput)).toThrow();
  });
});
""",
            "jest": """
import { function } from './module';

describe('function', () => {
  test('happy path', () => {
    const result = function(validInput);
    expect(result).toBe(expectedOutput);
  });
  
  test('edge case', () => {
    expect(() => function(invalidInput)).toThrow();
  });
});
"""
        }
        
        example = framework_examples.get(framework, "")
        
        return f"""Generate comprehensive unit tests for this {language} file using {framework}.

**FILE**: {file_path}

**SOURCE CODE**:
```{language}
{file_content}
```

**REQUIREMENTS**:
1. Test all exported functions/classes
2. Include happy path and edge cases
3. Use proper {framework} syntax and assertions
4. Include proper imports from the source file
5. Return ONLY the test code, no markdown, no explanations

**EXAMPLE STRUCTURE**:
{example}

Generate the complete test file now:"""

    def _clean_generated_code(self, response: str, language: str) -> str:
        """Cleans LLM response to extract pure code."""
        # Remove markdown code blocks
        response = re.sub(r'```(?:python|typescript|javascript|jsx|tsx)?\n', '', response)
        response = response.replace('```', '')
        
        # Remove language identifiers at start
        for lang in ["python", "typescript", "javascript", "pytest", "vitest", "jest"]:
            response = re.sub(f'^{lang}\\s+', '', response, flags=re.IGNORECASE)
        
        return response.strip()

    async def _write_test_files(
        self, 
        project_path: str, 
        test_files: Dict[str, str],
        sm
    ) -> None:
        """Writes generated test files to disk."""
        for test_path, test_content in test_files.items():
            full_path = os.path.join(project_path, test_path)
            
            # Create directory if needed
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            try:
                with open(full_path, 'w') as f:
                    f.write(test_content)
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"💾 Wrote {test_path}"})
            except Exception as e:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"⚠️ Failed to write {test_path}: {str(e)}"})

    async def _run_tests(
        self, 
        project_path: str, 
        framework: str,
        sm
    ) -> dict:
        """
        Executes tests using the detected framework.
        Returns structured test results.
        """
        if framework == "pytest":
            return await self._run_pytest(project_path, sm)
        elif framework == "vitest":
            return await self._run_vitest(project_path, sm)
        elif framework == "jest":
            return await self._run_jest(project_path, sm)
        else:
            return {
                "success": False,
                "framework": framework,
                "error": f"Framework {framework} not supported for execution"
            }

    async def _run_pytest(self, project_path: str, sm) -> dict:
        """Runs pytest and parses results."""
        backend_path = os.path.join(project_path, "backend")
        
        if not os.path.exists(backend_path):
            return {
                "success": False,
                "framework": "pytest",
                "error": "No backend directory found"
            }
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", "--tb=short"],
                cwd=backend_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Parse pytest output
            output = result.stdout + result.stderr
            
            # Extract test counts
            passed = len(re.findall(r'PASSED', output))
            failed = len(re.findall(r'FAILED', output))
            skipped = len(re.findall(r'SKIPPED', output))
            
            success = result.returncode == 0
            
            if success:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"✅ All tests passed! ({passed} passed)"})
            else:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"❌ {failed} tests failed"})
            
            return {
                "success": success,
                "framework": "pytest",
                "tests_run": passed + failed + skipped,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "details": output,
                "exit_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            await sm.emit("agent_log", {"agent_name": "TESTING", "message": "⚠️ Tests timed out after 30s"})
            return {
                "success": False,
                "framework": "pytest",
                "error": "Tests timed out after 30 seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "framework": "pytest",
                "error": f"Execution error: {str(e)}"
            }

    async def _run_vitest(self, project_path: str, sm) -> dict:
        """Runs vitest and parses results."""
        frontend_path = os.path.join(project_path, "frontend")
        
        if not os.path.exists(frontend_path):
            return {
                "success": False,
                "framework": "vitest",
                "error": "No frontend directory found"
            }
        
        try:
            # Check if vitest is installed
            result = subprocess.run(
                ["npm", "run", "test", "--", "--run"],
                cwd=frontend_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stdout + result.stderr
            
            # Parse vitest output
            passed = len(re.findall(r'✓', output))
            failed = len(re.findall(r'✗', output))
            
            success = result.returncode == 0
            
            if success:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"✅ All tests passed! ({passed} passed)"})
            else:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"❌ {failed} tests failed"})
            
            return {
                "success": success,
                "framework": "vitest",
                "tests_run": passed + failed,
                "passed": passed,
                "failed": failed,
                "skipped": 0,
                "details": output,
                "exit_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            await sm.emit("agent_log", {"agent_name": "TESTING", "message": "⚠️ Tests timed out after 60s"})
            return {
                "success": False,
                "framework": "vitest",
                "error": "Tests timed out after 60 seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "framework": "vitest",
                "error": f"Execution error: {str(e)}"
            }

    async def _run_jest(self, project_path: str, sm) -> dict:
        """Runs jest and parses results."""
        frontend_path = os.path.join(project_path, "frontend")
        
        if not os.path.exists(frontend_path):
            return {
                "success": False,
                "framework": "jest",
                "error": "No frontend directory found"
            }
        
        try:
            result = subprocess.run(
                ["npm", "test", "--", "--passWithNoTests"],
                cwd=frontend_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            output = result.stdout + result.stderr
            
            # Parse jest output
            passed_match = re.search(r'(\d+) passed', output)
            failed_match = re.search(r'(\d+) failed', output)
            
            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            
            success = result.returncode == 0
            
            if success:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"✅ All tests passed! ({passed} passed)"})
            else:
                await sm.emit("agent_log", {"agent_name": "TESTING", "message": f"❌ {failed} tests failed"})
            
            return {
                "success": success,
                "framework": "jest",
                "tests_run": passed + failed,
                "passed": passed,
                "failed": failed,
                "skipped": 0,
                "details": output,
                "exit_code": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            await sm.emit("agent_log", {"agent_name": "TESTING", "message": "⚠️ Tests timed out after 60s"})
            return {
                "success": False,
                "framework": "jest",
                "error": "Tests timed out after 60 seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "framework": "jest",
                "error": f"Execution error: {str(e)}"
            }

    async def quick_validate(self, project_path: str) -> dict:
        """
        Lightweight validation - checks if tests exist and can import.
        Does not run full test suite.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "TESTING", "message": "🔍 Quick validation check..."})
        
        # Check for test directories
        backend_tests = os.path.join(project_path, "backend", "tests")
        frontend_tests = os.path.join(project_path, "frontend", "__tests__")
        
        has_backend_tests = os.path.exists(backend_tests) and len(os.listdir(backend_tests)) > 0
        has_frontend_tests = os.path.exists(frontend_tests) and len(os.listdir(frontend_tests)) > 0
        
        return {
            "has_tests": has_backend_tests or has_frontend_tests,
            "backend_tests": has_backend_tests,
            "frontend_tests": has_frontend_tests,
            "recommendation": "Run full test suite" if (has_backend_tests or has_frontend_tests) else "No tests found to validate"
        }