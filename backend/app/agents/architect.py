# ACEA Sentinel - The Architect Agent (HYBRID)
# Uses Gemini API with automatic Ollama fallback
# Generalized: stack-agnostic via StackProfiles, input-sanitized, schema-validated

import json
import asyncio
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


class ArchitectAgent:
    def __init__(self):
        self.model = None

    async def design_system(self, user_prompt: str, tech_stack: str = "Auto-detect") -> dict:
        """
        Analyzes the user prompt and generates a MINIMAL, production-ready system architecture.
        Uses Hybrid client: Gemini API → Ollama fallback.
        
        Stack-agnostic: rules and examples are injected from StackProfiles.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        from app.core.cache import cache
        from app.core.stack_profiles import detect_stack, get_primary_stack_options
        from app.core.input_sanitizer import wrap_user_input, sanitize_user_prompt
        from app.core.schema_validator import validate_blueprint, safe_parse_json

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

        # ── Detect stack profile ──────────────────────────────
        profile = detect_stack(user_prompt, tech_stack)
        logger.info(f"Architect using stack profile: {profile.id} ({profile.display_name})")

        # ── Build dynamic rules from profile ──────────────────
        stack_rules = profile.get_architect_rules_text()
        stack_options = "|".join(get_primary_stack_options())

        # ── Wrap user input for injection safety ──────────────
        safe_user_prompt = wrap_user_input(user_prompt)

        system_prompt = f"""
You are The Architect, the brain of ACEA Sentinel.

**OBJECTIVE**: Design a MINIMAL, production-ready software system for this request:
{safe_user_prompt}

**TECH STACK PREFERENCE**: {tech_stack}
**SUGGESTED STACK PROFILE**: {profile.display_name} ({profile.category})

**AUTONOMY**: You are the Architect. Use the SUGGESTED stack unless the user's request CLEARLY implies a simpler or different approach (e.g. use Static HTML for a "simple page" even if Next.js is suggested). Choose the best tool for the job.

**CRITICAL RULES**:
1. **DEFAULT TO DYNAMIC**: "Dynamic" is the default project type. Only use "static" if the user EXPLICITLY requests a static site (e.g., "static html", "no backend").
2. **NO IMPLICIT STATIC**: The presence of HTML files does NOT make a project static.
3. **FILE LIMITS**:
   - SIMPLE: Max {profile.max_files_simple} files
   - MEDIUM: Max {profile.max_files_medium} files
   - COMPLEX: Max {profile.max_files_complex} files
4. **STACK-SPECIFIC RULES**:
{stack_rules if stack_rules else "   - No special rules for this stack."}

**OUTPUT FORMAT**: Return ONLY a JSON object (no markdown):
{{
    "project_name": "string",
    "description": "string",
    "project_type": "dynamic|static",
    "primary_stack": "{stack_options}",
    "rationale": "Short explanation for stack choice",
    "complexity": "simple|medium|complex",
    "tech_stack": "{tech_stack}",
    "file_structure": [
        {{"path": "path/to/file.ext", "description": "What this file does"}}
    ],
    "api_endpoints": [],
    "security_policies": ["Input validation", "CORS"]
}}

**IMPORTANT**: After your JSON output, include a thought signature:

THOUGHT_SIGNATURE:
{{
  "intent": "What you're designing",
  "rationale": "Why you chose this approach (1-2 sentences)",
  "confidence": 0.85,
  "alternatives_considered": ["Option A (rejected because...)", "Option B (rejected because...)"],
  "context_used": ["Tech stack preference", "Complexity assessment"],
  "predicted_outcome": "5 files, ~300 LOC, 10min to generate"
}}
"""

        max_attempts = 3
        errors = []

        for attempt in range(max_attempts):
            try:
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"Generating blueprint (Attempt {attempt+1}/{max_attempts})..."})

                response = await client.generate(system_prompt, json_mode=True)

                # ── Parse JSON using safe_parse_json ──────────
                result, parse_error = safe_parse_json(response)
                if result is None:
                    raise json.JSONDecodeError(parse_error or "Unknown parse error", response[:100], 0)

                # ── Validate against schema ───────────────────
                result, warnings = validate_blueprint(result)
                if result is None:
                    raise ValueError(f"Blueprint validation failed: {warnings}")
                if warnings:
                    logger.warning(f"Blueprint validated with {len(warnings)} warnings: {warnings[:3]}")

                file_count = len(result.get("file_structure", []))
                complexity = result.get("complexity", "simple")
                p_type = result.get("project_type", "dynamic")
                stack = result.get("primary_stack", "unknown")

                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"✅ Blueprint: {result['project_name']} ({p_type}/{stack}, {file_count} files)"})

                # ── SAFETY NET: Fix paths & add missing configs using profile ──
                files = result.get("file_structure", [])
                primary_stack = result.get("primary_stack", "").lower()

                # Re-detect profile from the LLM's output (it may have chosen differently)
                from app.core.stack_profiles import detect_stack_from_blueprint
                output_profile = detect_stack_from_blueprint(result)

                # Detect web project from profile
                is_web_project = output_profile.is_web

                # 1. For web projects with a source_prefix, ensure files go under that prefix
                if is_web_project and output_profile.source_prefix:
                    prefix = output_profile.source_prefix
                    for f in files:
                        curr_path = f["path"]
                        if not curr_path.startswith(prefix) and not curr_path.startswith("backend/"):
                            f["path"] = f"{prefix}{curr_path}"

                # 2. Stack-specific path normalization (e.g., strip src/ for Next.js App Router)
                if output_profile.id == "nextjs":
                    for f in files:
                        if f["path"].startswith("frontend/src/"):
                            f["path"] = f["path"].replace("frontend/src/", "frontend/", 1)

                    # Ensure App Router structure
                    paths = [f["path"] for f in files]
                    has_app = any("app/page.tsx" in p for p in paths)
                    has_pages = any("pages/index.tsx" in p for p in paths)

                    if not (has_app or has_pages):
                        for f in files:
                            if f["path"] == "frontend/page.tsx" or f["path"] == "frontend/index.tsx":
                                f["path"] = "frontend/app/page.tsx"

                # 3. Add essential configs from profile
                paths = [f["path"] for f in files]
                added_configs = []
                for conf_path, desc in output_profile.config_files.items():
                    if not any(conf_path in p for p in paths):
                        files.append({"path": conf_path, "description": desc})
                        added_configs.append(conf_path)

                # Update paths list after modifications
                paths = [f["path"] for f in files]

                if added_configs:
                    result["file_structure"] = files
                    await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"🔧 Architect added missing configs: {len(added_configs)} files"})

                # Cache successful result
                await cache.set(user_prompt, "architect", json.dumps(result), tech_stack=tech_stack)

                # --- Capture Thought Signature ---
                from app.core.thought_signature import capture_signature

                signature = await capture_signature(
                    agent_name="ARCHITECT",
                    prompt=system_prompt,
                    response=response,
                    token_usage=len(response) // 4,
                    model_used="gemini-2.0-flash-exp"
                )

                result["thought_signature"] = signature.to_dict()

                return result

            except json.JSONDecodeError as e:
                errors.append(f"JSON parse error: {str(e)[:50]}")
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"⚠️ JSON parse error, retrying..."})
                logger.warning(f"Architect JSON parse error attempt {attempt+1}: {e}")
                await asyncio.sleep(1)
                continue

            except Exception as e:
                error_str = str(e)
                errors.append(error_str[:100])
                await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"⚠️ Error: {error_str[:50]}..."})
                logger.error(f"Architect error attempt {attempt+1}: {error_str[:200]}")

                if "Ollama not available" in error_str:
                    break

                await asyncio.sleep(1)
                continue

        return {"error": f"Architect failed after {max_attempts} attempts. Errors: {errors}"}