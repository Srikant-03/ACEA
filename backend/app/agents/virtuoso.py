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
        files = await self.batch_generate_files(file_list, prompt_context, existing_files)
        
        # Emit file generation events for UI
        for path, code in files.items():
            await sm.emit("file_generated", {"path": path, "content": code, "status": "created"})
            
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"✅ Batch Complete: {len(files)} files created!"})
        return files

    async def batch_generate_files(self, file_list: list, context: str, existing_files: dict = None) -> dict:
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
6. INTELLIGENT DEPENDENCY MANAGEMENT:
   - You MUST generate a 'package.json' tailored to the specific Tech Stack.
   - USE "latest" for versions if unsure. DO NOT hallucinate specific version numbers like "5.9.3".
   - IF using Tailwind CSS: You MUST include 'tailwindcss', 'postcss', AND '@tailwindcss/postcss'.
   - IF generating 'postcss.config.mjs': Use 'export default {{ plugins: {{ "@tailwindcss/postcss": {{}} }} }};'
   - IF generating 'frontend/app/globals.css': Use '@import "tailwindcss";' (Tailwind 4 syntax).
   - IF using Next.js: 
        - Use minimal config: 'module.exports = {{ reactStrictMode: true }};'
        - DO NOT add custom 'webpack' rules unless explicitly requested (avoids Turbopack conflicts).
        - 'frontend/app/layout.tsx' MUST include <html> and <body> tags wrapping children.
        - STRICTLY forbid Vue syntax (<script setup>, ref from 'vue') in .tsx files. Use React useState/useEffect.
        - ALL Page components (page.tsx) MUST have an 'export default function'.
        - Next.js pages MUST be in 'frontend/app/' directory (e.g. 'frontend/app/page.tsx'), NOT 'frontend/src/'.
        - IMPORTANT: If using hooks (useState) in 'page.tsx', you MUST add "use client"; at the TOP of the file.
   - Do NOT assume any dependencies are pre-installed. You are the sole dependency manager.
7. Return ONLY the JSON object
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
        return await self.sequential_generate_files(file_list, context, existing_files)

    async def sequential_generate_files(self, file_list: list, context: str, existing_files: dict = None) -> dict:
        """Fallback: Generate files one at a time. Skips files that already exist."""
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        # Start with existing files to preserve progress
        files = existing_files.copy() if existing_files else {}
        
        for file_info in file_list:
            path = file_info.get("path")
            desc = file_info.get("description")
            
            # RESUMPTION LOGIC: If file exists and is not empty, skip it
            if path in files and files[path] and len(files[path].strip()) > 10:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⏩ Skipping {path} (already generated)"})
                continue
            
            await sm.emit("file_status", {"path": path, "status": "generating"})
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"Coding {path}..."})
            
            prompt = f"""
Generate production code for: {path}
Description: {desc}
Context: {context}

Return ONLY the code, no markdown blocks.

CRITICAL RULES:
1. IF generating 'package.json' with Tailwind: Include 'tailwindcss', 'postcss', AND '@tailwindcss/postcss'.
2. IF generating 'postcss.config.mjs': Use 'export default {{ plugins: {{ "@tailwindcss/postcss": {{}} }} }};'
3. IF generating 'frontend/app/globals.css': Use '@import "tailwindcss";' (Tailwind 4 syntax).
4. IF generating 'next.config.js': Use CommonJS 'module.exports = {{ reactStrictMode: true }};'
5. IF generating 'frontend/app/layout.tsx': MUST include <html> and <body> tags.
"""
            
            try:
                code = await client.generate(prompt)
                # Clean markdown
                # Clean markdown and common identifiers
                code = code.replace("```python", "").replace("```typescript", "").replace("```javascript", "").replace("```js", "").replace("```ts", "")
                code = code.replace("```tsx", "").replace("```json", "").replace("```", "").strip()
                
                # Extra safety: Remove bare language identifiers at start of file if present (common LLM artifact)
                for lang in ["javascript", "typescript", "python", "json", "tsx", "jsx", "js", "ts"]:
                     if re.match(f"^{lang}\\s+", code, re.IGNORECASE):
                          code = re.sub(f"^{lang}\\s+", "", code, flags=re.IGNORECASE).strip()
                files[path] = code
                
                # EMIT PARTIAL SUCCESS: Update UI immediately so user sees progress
                await sm.emit("file_generated", {"path": path, "content": code, "status": "created"})
                
            except Exception as e:
                files[path] = f"# Error generating {path}: {e}"
        
        return files
            
    async def repair_files(self, existing_files: dict, errors: list) -> dict:
        """
        SMART REPAIR: Fixes files based on error list or structured fix plans.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        files_to_fix = {} # path -> instruction
        
        # 1. Parse Errors/Fixes
        for item in errors:
            # Case A: Structured Fix (from TesterAgent)
            if isinstance(item, dict) and "file" in item and "change" in item:
                path = item["file"]
                instruction = item["change"]
                # Normalize path
                if path.startswith("/"): path = path[1:]
                files_to_fix[path] = instruction
                
            # Case B: String Error (Legacy/Raw)
            elif isinstance(item, str):
                # Try to extract file path using regex or fuzzy match
                # Regex "FILE: <path> - <instruction>"
                match = re.search(r"FILE:\s*([^\s]+)\s*-\s*(.*)", item, re.IGNORECASE)
                if match:
                    path = match.group(1).strip()
                    instruction = match.group(2).strip()
                    files_to_fix[path] = instruction
                else:
                    # Fallback: fuzzy match against existing files
                    for existing_path in existing_files.keys():
                        if existing_path in item or existing_path.split("/")[-1] in item:
                            files_to_fix[existing_path] = f"Fix error: {item}"
                            
        if not files_to_fix:
             await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ Could not identify specific files to fix. Retrying entire batch..."})
             return await self.sequential_generate_files([{"path": p} for p in existing_files], f"Fix errors: {errors}")

        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔧 Patching {len(files_to_fix)} files: {list(files_to_fix.keys())}"})
        
        repaired_files = existing_files.copy()
        
        for path, instruction in files_to_fix.items():
            # If path not in existing, it might be a new file suggestion
            original_code = existing_files.get(path, "")
            
            prompt = f"""
START REPAIR MISSION
TARGET: {path}
INSTRUCTION: {instruction}

ORIGINAL CODE:
{original_code}

TASK: Return the FIXED code for this file.
RULES:
1. Apply the instruction precisely.
2. Maintain existing functionality.
3. Return ONLY the code.
4. IF fixing 'next.config.js', ensure 'module.exports = {{ ... }}'.
5. IF fixing 'page.tsx', ensure NO Vue syntax (<script setup>) is used. Use React.
6. IF using React Hooks (useState, useEffect) in Next.js App Router, YOU MUST add 'use client'; at the very top.
"""
            try:
                new_code = await client.generate(prompt)
                # Clean
                # Clean markdown and common identifiers
                new_code = new_code.replace("```python", "").replace("```typescript", "").replace("```javascript", "").replace("```js", "").replace("```ts", "")
                new_code = new_code.replace("```tsx", "").replace("```json", "").replace("```", "").strip()
                
                # Extra safety: Remove bare language identifiers at start of file
                for lang in ["javascript", "typescript", "python", "json", "tsx", "jsx", "js", "ts"]:
                     if re.match(f"^{lang}\\s+", new_code, re.IGNORECASE):
                          new_code = re.sub(f"^{lang}\\s+", "", new_code, flags=re.IGNORECASE).strip()
                
                # OPTIMIZATION: Validate JSON immediately if fixing a JSON file
                if path.endswith(".json"):
                    try:
                        json.loads(new_code)
                    except json.JSONDecodeError:
                        # Attempt to sanitize (extract from first { to last })
                        try:
                            match = re.search(r"(\{.*\})", new_code, re.DOTALL)
                            if match:
                                san_code = match.group(1)
                                json.loads(san_code) # Verify again
                                new_code = san_code
                            else:
                                raise ValueError("Generated code is not valid JSON")
                        except Exception as json_err:
                            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Generated invalid JSON for {path}. Skipping save."})
                            continue # Skip processing this bad file
                            
                repaired_files[path] = new_code
                await sm.emit("file_generated", {"path": path, "content": new_code, "status": "repaired"})
            except Exception as e:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"Failed to patch {path}: {e}"})
                
        return repaired_files