# Smart Orchestrator - Optimized API Usage
# Combines architect+coder into single calls, uses caching and templates

import json
import hashlib
import copy
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime


class SmartOrchestrator:
    """
    Optimized project generation with:
    - Combined architect+coder prompts (1 API call instead of 2-3)
    - Response caching for similar requests
    - Template matching for common projects
    """
    
    def __init__(self):
        self.cache: Dict[str, dict] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        self.cache_ttl_hours = 24
    
    async def generate_project_optimized(
        self, 
        prompt: str, 
        tech_stack: Optional[str] = None,
        include_docs: bool = True
    ) -> Dict:
        """
        Optimized project generation with smart API usage.
        
        Returns:
        {
            "blueprint": {...},
            "files": {"path": "content", ...},
            "source": "template|cache|api"
        }
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        # Strategy 1: Check for matching template (0 API calls)
        template = self._match_template(prompt)
        if template and not tech_stack:
            await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "⚡ Using template (0 API calls)"})
            return {**template, "source": "template"}
        
        # Strategy 2: Check cache for similar prompts
        cache_key = self._get_cache_key(prompt, tech_stack)
        if cache_key in self.cache and self._is_cache_valid(cache_key):
            await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "💾 Using cached result (0 API calls)"})
            cached = self._customize_cached_project(self.cache[cache_key], prompt)
            return {**cached, "source": "cache"}
        
        # Strategy 3: Combined API call for architect+coder
        await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "🚀 Generating with combined prompt (1 API call)"})
        result = await self._combined_architect_coder(prompt, tech_stack)
        
        # Generate docs if requested
        if include_docs and "files" in result:
            readme = self._generate_simple_readme(result.get("blueprint", {}), prompt)
            result["files"]["README.md"] = readme
        
        # Cache the result
        self.cache[cache_key] = result
        self.cache_timestamps[cache_key] = datetime.now()
        
        return {**result, "source": "api"}
    
    async def _combined_architect_coder(self, prompt: str, tech_stack: Optional[str]) -> Dict:
        """
        Single API call that generates both blueprint AND all code files.
        """
        from app.core.local_model import HybridModelClient
        
        client = HybridModelClient()
        
        combined_prompt = f"""
You are an expert full-stack developer. Complete this task in ONE response.

USER REQUEST: {prompt}
TECH STACK: {tech_stack or 'Choose the best fit for the project'}

OUTPUT FORMAT - Return ONLY valid JSON:
{{
  "blueprint": {{
    "project_name": "my-project",
    "description": "Brief description",
    "projectType": "frontend|backend|fullstack",
    "tech_stack": "React + Node.js",
    "entrypoint": "npm start",
    "port": 3000
  }},
  "files": {{
    "src/App.jsx": "import React from \'react\';\\n\\nfunction App() {{\\n  return <div>Hello</div>;\\n}}\\n\\nexport default App;",
    "package.json": "{{\\\"name\\\": \\\"my-app\\\", \\\"version\\\": \\\"1.0.0\\\"}}",
    "index.html": "<!DOCTYPE html>..."
  }}
}}

REQUIREMENTS:
- Complete, runnable code (no TODOs or placeholders)
- Minimal dependencies
- Production-ready
- Include ALL files needed to run the project
- Maximum 15 files for simple projects
"""
        
        try:
            response = await client.generate(combined_prompt, json_mode=True)
            result = json.loads(response)
            
            # Ensure files is a dict
            if isinstance(result.get("files"), list):
                files_dict = {}
                for f in result["files"]:
                    files_dict[f["path"]] = f.get("content", "")
                result["files"] = files_dict
            
            return result
        except Exception as e:
            return {
                "blueprint": {"project_name": "error", "error": str(e)},
                "files": {}
            }
    
    def _match_template(self, prompt: str) -> Optional[Dict]:
        """Check if prompt matches a pre-built template."""
        prompt_lower = prompt.lower()
        
        templates_dir = Path(__file__).parent.parent / "templates"
        if not templates_dir.exists():
            return None
        
        # Keyword matching
        keywords = {
            "react-counter": ["counter", "increment", "decrement", "click counter"],
            "vanilla-todo": ["todo", "task list", "checklist", "to-do"],
            "calculator": ["calculator", "basic calculator", "simple calculator"],
        }
        
        for template_name, words in keywords.items():
            if any(word in prompt_lower for word in words):
                template_path = templates_dir / template_name
                if template_path.exists():
                    return self._load_template(template_path)
        
        return None
    
    def _load_template(self, template_path: Path) -> Dict:
        """Load template from disk."""
        blueprint_file = template_path / "blueprint.json"
        blueprint = {}
        
        if blueprint_file.exists():
            with open(blueprint_file) as f:
                blueprint = json.load(f)
        
        files = {}
        for file_path in template_path.rglob("*"):
            if file_path.is_file() and file_path.name != "blueprint.json":
                rel_path = str(file_path.relative_to(template_path))
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    files[rel_path] = f.read()
        
        return {"blueprint": blueprint, "files": files}
    
    def _get_cache_key(self, prompt: str, tech_stack: Optional[str]) -> str:
        """Generate cache key from prompt."""
        key = f"{prompt.lower().strip()}:{tech_stack or 'auto'}"
        return hashlib.md5(key.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self.cache_timestamps:
            return False
        age = (datetime.now() - self.cache_timestamps[cache_key]).total_seconds() / 3600
        return age < self.cache_ttl_hours
    
    def _customize_cached_project(self, cached: Dict, prompt: str) -> Dict:
        """Slightly modify cached project for uniqueness."""
        result = copy.deepcopy(cached)
        
        # Update package name if package.json exists
        if "package.json" in result.get("files", {}):
            try:
                pkg = json.loads(result["files"]["package.json"])
                pkg["name"] = prompt.lower().replace(" ", "-")[:30]
                result["files"]["package.json"] = json.dumps(pkg, indent=2)
            except Exception as e:
                # Log error but continue returning cached result
                print(f"Cache customization error: {e}")
        
        return result
    
    def _generate_simple_readme(self, blueprint: dict, prompt: str) -> str:
        """Generate basic README without API call."""
        name = blueprint.get("project_name", "Project")
        desc = blueprint.get("description", prompt)
        stack = blueprint.get("tech_stack", "Unknown")
        
        return f"""# {name}

## Description
{desc}

## Tech Stack
{stack}

## Installation
```bash
npm install   # For Node.js projects
pip install -r requirements.txt   # For Python projects
```

## Run
```bash
npm start   # For Node.js
python main.py   # For Python
```
"""

    async def update_single_file(
        self, 
        project_id: str,
        file_path: str,
        current_content: str,
        instruction: str
    ) -> str:
        """
        AI-powered single file update.
        Uses minimal API call - only modifies one file.
        """
        from app.core.local_model import HybridModelClient
        from app.core.filesystem import update_file_content
        
        client = HybridModelClient()
        
        prompt = f"""
You are a code editor. Modify this file according to the instruction.

FILE: {file_path}

CURRENT CONTENT:
```
{current_content}
```

INSTRUCTION: {instruction}

OUTPUT: Return ONLY the updated file content, nothing else. No explanations, no markdown formatting.
"""
        
        response = await client.generate(prompt)
        
        # Clean response
        updated = response.strip()
        if updated.startswith("```"):
            lines = updated.split("\n")
            updated = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        # Save
        update_file_content(project_id, file_path, updated)
        
        return updated


# Singleton
_smart_orchestrator = None

def get_smart_orchestrator() -> SmartOrchestrator:
    global _smart_orchestrator
    if _smart_orchestrator is None:
        _smart_orchestrator = SmartOrchestrator()
    return _smart_orchestrator
