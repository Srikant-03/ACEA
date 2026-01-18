# ACEA Sentinel - The Architect Agent (HYBRID)
# Uses Gemini API with automatic Ollama fallback

from app.core.config import settings
import json
import asyncio
import re

class ArchitectAgent:
    def __init__(self):
        self.model = None

    async def design_system(self, user_prompt: str) -> dict:
        """
        Analyzes the user prompt and generates a MINIMAL, production-ready system architecture.
        Uses Hybrid client: Gemini API → Ollama fallback.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": "Analyzing requirements..."})

        system_prompt = f"""
You are The Architect, the brain of ACEA Sentinel.

**OBJECTIVE**: Design a MINIMAL, production-ready software system for this request:
"{user_prompt}"

**CRITICAL FILE COUNT LIMITS**:
🟢 SIMPLE (todo, calculator, tic-tac-toe, timer, counter): MAX 5-8 files
🟡 MEDIUM (blog, dashboard, chat app, weather app): MAX 10-15 files
🔴 COMPLEX (e-commerce, social media, booking system): MAX 18-25 files

**TECH STACK**: Next.js 15 + FastAPI + SQLite

**OUTPUT FORMAT**: Return ONLY a JSON object (no markdown):
{{
    "project_name": "string",
    "description": "string",
    "complexity": "simple|medium|complex",
    "tech_stack": "Next.js 15 + FastAPI + SQLite",
    "file_structure": [
        {{"path": "frontend/app/page.tsx", "description": "Main page with game UI"}},
        {{"path": "backend/app/main.py", "description": "FastAPI server"}}
    ],
    "api_endpoints": [],
    "security_policies": ["Input validation", "CORS"]
}}

**EXAMPLES**:
Tic-Tac-Toe (5 files): page.tsx, layout.tsx, globals.css, main.py, requirements.txt
Todo App (7 files): page.tsx, layout.tsx, globals.css, main.py, database.py, models.py, requirements.txt
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
                
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"✅ Blueprint: {result['project_name']} ({file_count} files, {complexity})"})
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