# ACEA Sentinel - The Virtuoso Agent (HYBRID)
# Batch code generation with Gemini API + Ollama fallback

from app.core.config import settings
import asyncio
import re
import json

class VirtuosoAgent:
    def __init__(self):
        self.model = None

    async def generate_from_blueprint(self, blueprint: dict, existing_files: dict = None, errors: list = None) -> dict:
        """
        Generates complete file system based on blueprint.
        Uses batch generation to minimize API calls.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "Analyzing Blueprint..."})

        file_list = blueprint.get("file_structure", [])
        
        if not file_list:
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "Blueprint empty. Defaulting to main.py"})
            file_list = [{"path": "main.py", "description": "Main entry point script"}]

        prompt_context = f"Project: {blueprint.get('project_name')}\nStack: {blueprint.get('tech_stack', 'Next.js + FastAPI')}"
        if errors:
            prompt_context += f"\nFIX THESE ERRORS: {errors}"
            
        print(f"Virtuoso: BATCH generating {len(file_list)} files...")
        await sm.emit("generation_started", {"total_files": len(file_list), "file_list": [f["path"] for f in file_list]})

        # BATCH: Generate all files in one call
        files = await self.batch_generate_files(file_list, prompt_context)
        
        # Emit file generation events for UI
        for path, code in files.items():
            await sm.emit("file_generated", {"path": path, "content": code, "status": "created"})
            
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"✅ Batch Complete: {len(files)} files created!"})
        return files

    async def batch_generate_files(self, file_list: list, context: str) -> dict:
        """
        Generate ALL files in ONE API call using hybrid client.
        Falls back to Ollama if Gemini quota exhausted.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        # Build file specification
        file_specs = "\n".join([
            f"FILE: {f['path']}\nDESCRIPTION: {f['description']}\n"
            for f in file_list
        ])
        
        prompt = f"""
You are The Virtuoso, an expert code generator.

CONTEXT: {context}

TASK: Generate ALL files for this project in ONE response.

FILES TO GENERATE:
{file_specs}

OUTPUT FORMAT (CRITICAL):
Return a valid JSON object where:
- Keys are file paths (strings)
- Values are complete file contents (strings)

Example:
{{
    "frontend/app/page.tsx": "import React from 'react'\\n\\nexport default function Page() {{\\n  return <div>Hello</div>\\n}}",
    "backend/main.py": "from fastapi import FastAPI\\n\\napp = FastAPI()\\n\\n@app.get('/')\\ndef root():\\n    return {{'message': 'Hello'}}"
}}

RULES:
1. NO markdown code blocks
2. Production-ready, complete code
3. Include all imports
4. Proper JSON escaping
5. Return ONLY the JSON object
"""
        
        max_attempts = 3
        
        for attempt in range(max_attempts):
            try:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"Batch generation (Attempt {attempt+1}/{max_attempts})..."})
                
                response = await client.generate(prompt, json_mode=True)
                
                # Parse JSON
                files_dict = json.loads(response)
                
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"✅ Generated {len(files_dict)} files in batch"})
                return files_dict
                
            except json.JSONDecodeError as e:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ JSON parse error: {str(e)[:50]}"})
                await asyncio.sleep(1)
                continue
                
            except Exception as e:
                error_str = str(e)
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Error: {error_str[:50]}..."})
                
                if "Ollama not available" in error_str:
                    break
                    
                await asyncio.sleep(1)
                continue
        
        # Fallback: Sequential generation
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ Batch failed. Using sequential generation..."})
        return await self.sequential_generate_files(file_list, context)

    async def sequential_generate_files(self, file_list: list, context: str) -> dict:
        """Fallback: Generate files one at a time."""
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        files = {}
        for file_info in file_list:
            path = file_info.get("path")
            desc = file_info.get("description")
            
            await sm.emit("file_status", {"path": path, "status": "generating"})
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"Coding {path}..."})
            
            prompt = f"""
Generate production code for: {path}
Description: {desc}
Context: {context}

Return ONLY the code, no markdown blocks.
"""
            
            try:
                code = await client.generate(prompt)
                # Clean markdown
                code = code.replace("```python", "").replace("```typescript", "")
                code = code.replace("```tsx", "").replace("```", "").strip()
                files[path] = code
            except Exception as e:
                files[path] = f"# Error generating {path}: {e}"
            
        return files