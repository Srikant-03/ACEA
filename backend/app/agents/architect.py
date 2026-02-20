# ACEA Sentinel - The Architect Agent (HYBRID)
# Uses Gemini API with automatic Ollama fallback

from app.core.config import settings
import json
import asyncio
import re

class ArchitectAgent:
    def __init__(self):
        self.model = None

    async def design_system(self, user_prompt: str, tech_stack: str = "Auto-detect") -> dict:
        """
        Analyzes the user prompt and generates a MINIMAL, production-ready system architecture.
        Uses Hybrid client: Gemini API → Ollama fallback.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        from app.core.cache import cache
        
        client = HybridModelClient()
        sm = SocketManager()
        
        # Initialize Redis (optional, non-blocking)
        await cache.init_redis()
        
        # Check Cache
        cached_response = await cache.get(user_prompt, "architect", tech_stack=tech_stack)
        if cached_response:
            await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": "⚡ Retrieved blueprint from cache"})
            return json.loads(cached_response)
        
        await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"Analyzing requirements (Stack: {tech_stack})..."})

        system_prompt = f"""
You are The Architect, the brain of ACEA Sentinel.

**OBJECTIVE**: Design a MINIMAL, production-ready software system for this request:
"{user_prompt}"

**TECH STACK PREFERENCE**: {tech_stack}

**CRITICAL RULES**:
1. **DEFAULT TO DYNAMIC**: "Dynamic" is the default project type. Only use "static" if the user EXPLICITLY requests a static site (e.g., "static html", "no backend").
2. **NO IMPLICIT STATIC**: The presence of HTML files does NOT make a project static.
3. **FILE LIMITS**:
   - SIMPLE: Max 5-8 files
   - MEDIUM: Max 10-15 files
   - COMPLEX: Max 18-25 files

**OUTPUT FORMAT**: Return ONLY a JSON object (no markdown):
{{
    "project_name": "string",
    "description": "string",
    "project_type": "dynamic|static",
    "primary_stack": "nextjs|vite|react|python|node|static",
    "rationale": "Short explanation for stack choice",
    "complexity": "simple|medium|complex",
    "tech_stack": "{tech_stack}",
    "file_structure": [
        {{"path": "frontend/app/page.tsx", "description": "Main page with game UI"}},
        {{"path": "backend/app/main.py", "description": "FastAPI server"}}
    ],
    "api_endpoints": [],
    "security_policies": ["Input validation", "CORS"]
}}

**EXAMPLES**:
1. User: "Make a portfolio" -> project_type: "dynamic", primary_stack: "nextjs"
2. User: "Static HTML landing page" -> project_type: "static", primary_stack: "static"
3. User: "Python script" -> project_type: "dynamic", primary_stack: "python"
"""
        
        max_attempts = 3
        errors = []
        
        for attempt in range(max_attempts):

            try:
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"Generating blueprint (Attempt {attempt+1}/{max_attempts})..."})
                
                response = await client.generate(system_prompt, json_mode=True)
                
                # Clean and parse response
                cleaned = response.replace("```json", "").replace("```", "").strip()
                result = json.loads(cleaned)
                
                file_count = len(result.get("file_structure", []))
                complexity = result.get("complexity", "simple")
                p_type = result.get("project_type", "dynamic")
                stack = result.get("primary_stack", "unknown")
                
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"✅ Blueprint: {result['project_name']} ({p_type}/{stack}, {file_count} files)"})
                
                # --- SAFETY NET: Ensure Config Files Exist & Paths are Correct ---
                files = result.get("file_structure", [])
                
                # 1. Enforce 'frontend/' prefix for web files if missing
                for f in files:
                    curr_path = f["path"]
                    if not curr_path.startswith("frontend/") and not curr_path.startswith("backend/"):
                        # Heuristic: .tsx, .jsx, .css, .html -> frontend
                        if any(ext in curr_path for ext in [".tsx", ".jsx", ".css", ".html", "vite", "next", "tailwind"]):
                            f["path"] = f"frontend/{curr_path}"
                            
                paths = [f["path"] for f in files]
                added_configs = []

                # 2. Add Configs based on Stack Detection
                tech_stack_val = result.get("tech_stack", "")
                tech_stack_str = tech_stack_val if isinstance(tech_stack_val, str) else " ".join(tech_stack_val) if isinstance(tech_stack_val, list) else str(tech_stack_val)
                is_nextjs = "next" in tech_stack_str.lower() or any("next.config" in p for p in paths) or any("app/page.tsx" in p for p in paths)
                
                # FIX: Ensure next.js uses app router structure if detecting nextjs
                if is_nextjs:
                     # Check if we have app/page.tsx
                     has_app = any("app/page.tsx" in p for p in paths)
                     has_pages = any("pages/index.tsx" in p for p in paths)
                     
                     if not (has_app or has_pages):
                         # Force app directory structure for main page if missing
                         for f in files:
                             if f["path"] == "frontend/page.tsx" or f["path"] == "frontend/index.tsx":
                                 f["path"] = "frontend/app/page.tsx"
                                 
                is_vite = "vite" in tech_stack_str.lower() or "react" in tech_stack_str.lower() or any("vite.config" in p for p in paths)

                if is_nextjs:
                    next_configs = {
                        "frontend/tailwind.config.ts": "Tailwind CSS configuration",
                        "frontend/postcss.config.mjs": "PostCSS configuration",
                        "frontend/next.config.js": "Next.js configuration",
                        "frontend/tsconfig.json": "TypeScript configuration"
                    }
                    for path, desc in next_configs.items():
                        if not any(path in p for p in paths):
                            files.append({"path": path, "description": desc})
                            added_configs.append(path)
                            
                elif is_vite:
                     vite_configs = {
                        "frontend/vite.config.js": "Vite configuration",
                        "frontend/tailwind.config.js": "Tailwind CSS configuration",
                        "frontend/postcss.config.js": "PostCSS configuration",
                        "frontend/package.json": "Package manifest"
                    }
                     for path, desc in vite_configs.items():
                        if not any(path in p for p in paths):
                            files.append({"path": path, "description": desc})
                            added_configs.append(path)
                
                if added_configs:
                    result["file_structure"] = files
                    await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"🔧 Architect added missing configs: {len(added_configs)} files"})

                # Cache successful result
                await cache.set(user_prompt, "architect", json.dumps(result), tech_stack=tech_stack)
                
                return result
                
            except json.JSONDecodeError as e:
                errors.append(f"JSON parse error: {str(e)[:50]}")
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"⚠️ JSON parse error, retrying..."})
                await asyncio.sleep(1)
                continue
                
            except Exception as e:
                error_str = str(e)
                errors.append(error_str[:100])
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"⚠️ Error: {error_str[:50]}..."})
                
                # If Ollama not available, don't keep retrying
                if "Ollama not available" in error_str:
                    break
                
                await asyncio.sleep(1)
                continue

        return {"error": f"Architect failed after {max_attempts} attempts. Errors: {errors}"}