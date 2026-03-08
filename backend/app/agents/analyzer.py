"""
Repository Analyzer Agent
Analyzes existing codebases to understand structure and context.
"""

import logging
import os
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class AnalyzerAgent:
    """
    Analyzes repository structure and generates context for planning.
    
    Uses:
    1. File structure analysis
    2. Dependency detection
    3. Test framework identification
    4. Entry point discovery
    """
    
    def __init__(self):
        pass
    
    async def analyze_codebase(
        self,
        repo_path: str,
        objective: str
    ) -> Dict[str, Any]:
        """
        Analyze repository and generate context.
        
        Args:
            repo_path: Path to repository
            objective: User's objective for analysis focus
            
        Returns:
            Analysis dict with structure, dependencies, recommendations
        """
        from app.core.HybridModelClient import HybridModelClient
        from app.core.key_manager import KeyManager
        from app.core.config import settings
        
        # Initialize client - handle case where keys might be missing in tests
        try:
            key_manager = KeyManager(settings.api_keys_list)
            client = HybridModelClient(key_manager)
        except Exception as e:
            logger.warning(f"Failed to initialize AI client: {e}")
            client = None
        
        repo_path = Path(repo_path)
        
        # 1. Gather file structure
        file_tree = self._build_file_tree(repo_path)
        
        # 2. Identify key files
        key_files = self._identify_key_files(repo_path)
        
        # 3. Read relevant files for context
        file_contents = self._read_key_files(repo_path, key_files)
        
        # 4. Detect tech stack
        tech_stack = self._detect_tech_stack(repo_path, key_files)
        
        gemini_analysis = {}
        
        # 5. Ask Gemini for analysis (if client available)
        if client:
            analysis_prompt = f"""
Analyze this codebase to help accomplish the objective: "{objective}"

**File Structure:**
{file_tree}

**Tech Stack Detected:**
{tech_stack}

**Key Files:**
{list(key_files.keys())}

**Sample Contents:**
{self._format_file_contents(file_contents, max_chars=3000)}

**TASK:**
1. Identify relevant files for the objective
2. Suggest which files need modification
3. Identify potential risks or dependencies
4. Recommend testing approach

Return JSON:
{{
  "relevant_files": ["path1", "path2"],
  "modification_targets": ["file_to_edit1", "file_to_edit2"],
  "dependencies": ["dep1", "dep2"],
  "risks": ["risk1", "risk2"],
  "testing_strategy": "Description"
}}
"""
            
            try:
                response = await client.generate(analysis_prompt, json_mode=True)
                # Clean up response
                cleaned_response = response.replace("```json", "").replace("```", "").strip()
                gemini_analysis = json.loads(cleaned_response, strict=False)
                
            except Exception as e:
                logger.error(f"Analysis failed: {e}")
                gemini_analysis = {"error": str(e)}
        else:
             gemini_analysis = {"message": "AI analysis skipped (no client)"}

        return {
            "success": True,
            "file_tree": file_tree,
            "tech_stack": tech_stack,
            "key_files": list(key_files.keys()),
            "gemini_analysis": gemini_analysis
        }
    
    def _build_file_tree(self, repo_path: Path, max_depth: int = 3) -> str:
        """Build visual file tree."""
        lines = []
        
        def walk_tree(path: Path, prefix: str = "", depth: int = 0):
            if depth > max_depth:
                return
            
            if path.name.startswith('.') or path.name in ['node_modules', '__pycache__', 'venv', 'env']:
                return
            
            if path.is_dir():
                lines.append(f"{prefix}📁 {path.name}/")
                try:
                    # Sort directories first, then files
                    children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
                    for child in children[:20]:  # Limit to 20 items per dir
                        walk_tree(child, prefix + "  ", depth + 1)
                except PermissionError:
                    pass
            else:
                lines.append(f"{prefix}📄 {path.name}")
        
        if repo_path.exists():
            walk_tree(repo_path)
        else:
             lines.append(f"Folder not found: {repo_path}")
             
        return "\n".join(lines[:200])  # Limit total lines
    
    def _identify_key_files(self, repo_path: Path) -> Dict[str, str]:
        """Identify important files to analyze."""
        key_files = {}
        
        # Common important files
        important_names = [
            'README.md', 'package.json', 'requirements.txt',
            'Dockerfile', 'docker-compose.yml',
            'setup.py', 'pyproject.toml', 'Cargo.toml',
            'go.mod', 'pom.xml', 'build.gradle',
            '.env.example', 'config.py', 'settings.py',
            'next.config.js', 'vite.config.js', 'tsconfig.json'
        ]
        
        if not repo_path.exists():
            return {}

        # Check root files
        for file_name in important_names:
            file_path = repo_path / file_name
            if file_path.exists():
                key_files[file_name] = str(file_path)
        
        # Entry points (search recursively but shallowly or specifically)
        entry_candidates = [
            'main.py', 'app.py', 'index.js', 'index.ts',
            'main.go', 'main.rs', 'server.js', 'page.tsx', 'layout.tsx'
        ]
        
        for entry in entry_candidates:
            # Simple recursive search limited to 2 levels to avoid deep traversals
            for match in repo_path.rglob(entry):
                # optimization: don't traverse into node_modules or venv
                if "node_modules" in str(match) or "venv" in str(match):
                    continue
                    
                try:
                    rel_path = match.relative_to(repo_path)
                    if len(rel_path.parts) <= 3: # Only close to root
                        key_files[str(rel_path)] = str(match)
                except ValueError:
                    pass
        
        return key_files
    
    def _read_key_files(
        self,
        repo_path: Path,
        key_files: Dict[str, str],
        max_size: int = 5000
    ) -> Dict[str, str]:
        """Read contents of key files."""
        contents = {}
        
        # Prioritize key files: README, config, then code
        sorted_keys = sorted(key_files.keys(), key=lambda k: 0 if 'README' in k else 1)
        
        for file_name in sorted_keys[:10]:  # Limit to 10 files
            file_path = key_files[file_name]
            try:
                path = Path(file_path)
                if path.stat().st_size > max_size:
                    contents[file_name] = f"[File too large: {path.stat().st_size} bytes - Truncated]\n"
                    # Read partial?
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        contents[file_name] += f.read(max_size)
                    continue
                
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    contents[file_name] = f.read()[:max_size]
                    
            except Exception as e:
                contents[file_name] = f"[Error reading: {e}]"
        
        return contents
    
    def _detect_tech_stack(self, repo_path: Path, key_files: Dict[str, str]) -> Dict[str, Any]:
        """Detect tech stack from files."""
        tech_stack = {
            "languages": [],
            "frameworks": [],
            "tools": []
        }
        
        # Language detection
        if any(k.endswith('package.json') for k in key_files):
            tech_stack["languages"].append("JavaScript/TypeScript")
        if any(k.endswith('requirements.txt') for k in key_files) or any(k.endswith('setup.py') for k in key_files):
            tech_stack["languages"].append("Python")
        if any(k.endswith('go.mod') for k in key_files):
            tech_stack["languages"].append("Go")
        if any(k.endswith('Cargo.toml') for k in key_files):
            tech_stack["languages"].append("Rust")
            
        # Deduplicate
        tech_stack["languages"] = list(set(tech_stack["languages"]))
        
        # Framework detection
        # Check package.json content
        pkg_files = [v for k, v in key_files.items() if k.endswith('package.json')]
        for pkg_path in pkg_files:
            try:
                with open(pkg_path, 'r') as f:
                    pkg = json.load(f)
                    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
                    
                    if 'next' in deps:
                        tech_stack["frameworks"].append("Next.js")
                        tech_stack["languages"].append("TypeScript") # Implicit usually
                    if 'react' in deps:
                        tech_stack["frameworks"].append("React")
                    if 'vue' in deps:
                        tech_stack["frameworks"].append("Vue")
                    if 'tailwindcss' in deps:
                        tech_stack["frameworks"].append("Tailwind CSS")
            except Exception:
                pass
        
        # Check requirements.txt
        req_files = [v for k, v in key_files.items() if k.endswith('requirements.txt')]
        for req_path in req_files:
            try:
                with open(req_path, 'r') as f:
                    reqs = f.read().lower()
                    if 'fastapi' in reqs:
                        tech_stack["frameworks"].append("FastAPI")
                    if 'flask' in reqs:
                        tech_stack["frameworks"].append("Flask")
                    if 'django' in reqs:
                        tech_stack["frameworks"].append("Django")
            except Exception:
                pass
                
        tech_stack["frameworks"] = list(set(tech_stack["frameworks"]))
        
        # Tools
        if any(k.endswith('Dockerfile') for k in key_files):
            tech_stack["tools"].append("Docker")
        if (repo_path / '.github').exists():
            tech_stack["tools"].append("GitHub Actions")
        
        return tech_stack
    
    def _format_file_contents(self, contents: Dict[str, str], max_chars: int) -> str:
        """Format file contents for prompt."""
        formatted = []
        total_chars = 0
        
        for file_name, content in contents.items():
            if total_chars >= max_chars:
                break
            
            snippet = content[:500]  # First 500 chars per file
            formatted.append(f"\n--- {file_name} ---\n{snippet}\n")
            total_chars += len(snippet)
        
        return "".join(formatted)


# Singleton
_analyzer_agent = None

def get_analyzer_agent() -> AnalyzerAgent:
    """Get singleton AnalyzerAgent."""
    global _analyzer_agent
    if _analyzer_agent is None:
        _analyzer_agent = AnalyzerAgent()
    return _analyzer_agent
