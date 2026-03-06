# ACEA Sentinel - The Virtuoso Agent (HYBRID)
# Batch code generation with Gemini API + Ollama fallback
# Generalized: stack-agnostic via StackProfiles, schema-validated

import asyncio
import re
import json
import logging

from app.core.config import settings
from app.core.stack_profiles import StackProfile

logger = logging.getLogger(__name__)


def _server_config_candidates(existing_files: dict, include_package: bool = False) -> list:
    """
    Return a list of server/config file paths that actually exist in the project.
    Tries both frontend/ (nested) and root (flat) paths.
    """
    base_names = ["server.js", "index.js", "app.js"]
    if include_package:
        base_names.append("package.json")
    
    found = []
    for name in base_names:
        # Try nested first, then root
        for candidate in [f"frontend/{name}", name]:
            if candidate in existing_files:
                found.append(candidate)
                break  # Don't add both for same base name
    return found


class VirtuosoAgent:
    def __init__(self):
        self.model = None

    async def generate_from_blueprint(self, blueprint: dict, existing_files: dict = None, errors: list = None) -> dict:
        """
        Generates complete file system based on blueprint.
        Uses batch generation to minimize API calls.
        
        TARGETED FIX MODE: When errors exist and existing_files are provided,
        routes through repair_files_targeted to only fix broken files instead
        of regenerating the entire project.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "Analyzing Blueprint..."})

        # TARGETED FIX MODE: Only fix broken files instead of full regeneration
        if errors and existing_files and len(existing_files) > 0:
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🎯 Targeted fix mode: {len(errors)} errors to resolve (preserving {len(existing_files)} existing files)"})
            
            # Extract affected file paths from errors
            affected_files = self._extract_affected_files(errors, existing_files)
            
            if affected_files:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔧 Targeting {len(affected_files)} files: {affected_files[:5]}"})
                repaired = await self.repair_files_targeted(
                    current_files=existing_files,
                    affected_files=affected_files,
                    fix_suggestions=[str(e) for e in errors]
                )
                # Normalize paths in repaired result
                repaired = self._normalize_file_paths(repaired)
                return {"files": repaired, "signature": None}
            else:
                # Could not identify specific files — fall back to repair_files
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ Could not identify specific files. Using fuzzy repair..."})
                repaired = await self.repair_files(existing_files, errors)
                repaired = self._normalize_file_paths(repaired)
                return {"files": repaired, "signature": None}

        file_list = blueprint.get("file_structure", [])
        
        if not file_list:
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "Blueprint empty. Defaulting to main.py"})
            file_list = [{"path": "main.py", "description": "Main entry point script"}]

        prompt_context = f"Project: {blueprint.get('project_name')}\nStack: {blueprint.get('tech_stack', 'Auto-detect')}"
        if errors:
            prompt_context += f"\nFIX THESE ERRORS: {errors}"
            
        logger.info(f"Virtuoso: BATCH generating {len(file_list)} files...")
        await sm.emit("generation_started", {"total_files": len(file_list), "file_list": [f["path"] for f in file_list]})

        # BATCH: Generate all files in one call
        # Returns {"files": ..., "signature": ...}
        result = await self.batch_generate_files(file_list, prompt_context, existing_files)
        
        # Handle legacy return (just dict) or new return (dict with keys)
        if isinstance(result, dict) and "files" in result:
             files = result["files"]
             signature = result.get("signature")
        else:
             files = result
             signature = None
        
        # Normalize all file paths (forward-slash, dedup)
        files = self._normalize_file_paths(files)
        
        # POST-GENERATION SANITIZER: Remove files forbidden by the stack profile
        from app.core.stack_profiles import detect_stack
        detected_stack = blueprint.get('tech_stack', 'Auto-detect')
        profile = detect_stack(blueprint.get('project_name', ''), detected_stack)
        files, removed = self._sanitize_for_profile(files, profile)
        if removed:
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🧹 Sanitizer removed {len(removed)} forbidden files: {removed}"})
        
        # Emit file generation events for UI
        for path, code in files.items():
            await sm.emit("file_generated", {"path": path, "content": code, "status": "created"})
            
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"✅ Batch Complete: {len(files)} files created!"})
        
        return {"files": files, "signature": signature}

    async def batch_generate_files(self, file_list: list, context: str, existing_files: dict = None) -> dict:
        """
        Generate ALL files in ONE API call using hybrid client.
        Falls back to Ollama if Gemini quota exhausted.
        Stack-agnostic: rules injected from StackProfile.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        from app.core.stack_profiles import detect_stack_from_blueprint
        from app.core.schema_validator import validate_generated_files
        
        client = HybridModelClient()
        sm = SocketManager()
        
        # Detect stack profile from context for rule injection
        # Parse stack from context string (e.g. "Stack: nextjs")
        detected_stack = "auto"
        if "Stack:" in context:
            detected_stack = context.split("Stack:")[1].strip().split("\n")[0].strip()
        
        from app.core.stack_profiles import detect_stack
        profile = detect_stack("", detected_stack)
        stack_rules = profile.get_virtuoso_rules_text()
        
        # Build file specification
        file_specs = "\n".join([
            f"FILE: {f['path']}\nDESCRIPTION: {f.get('description', '')}\n"
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
    "path/to/main.ext": "import ...\\n\\n// Complete implementation",
    "path/to/config.ext": "// Configuration file content"
}}

RULES:
1. NO markdown code blocks
2. Production-ready, complete code
3. Include all imports
4. Proper JSON escaping
5. INTELLIGENT DEPENDENCY MANAGEMENT:
   - Generate the appropriate dependency manifest for the stack ({profile.dependency_manifest or 'as needed'}).
   - Use a recent stable major version for all dependencies (e.g. "^18.0.0"). NEVER use "latest".
   - Do NOT assume any dependencies are pre-installed. You are the sole dependency manager.
6. STACK-SPECIFIC RULES ({profile.display_name}):
{stack_rules if stack_rules else "   No special rules for this stack."}
7. IMPORT PATH RULES (all frameworks):
   - Verify import paths match the EXACT file paths you generate.
   - Count directory levels carefully when using relative imports.
8. COMPULSORY: Include a "__thought_signature__" key (as the first key) with this structure:
   {{
     "intent": "Generating complete project files",
     "rationale": "Explain your tech stack and structure choices",
     "confidence": 0.9,
     "alternatives_considered": ["Alternative A", "Alternative B"],
     "context_used": ["Blueprint", "User Prompt"],
     "predicted_outcome": "Complete implementation"
   }}
9. Return ONLY the JSON object
"""
        
        max_attempts = 3
        last_response = None
        
        for attempt in range(max_attempts):
            try:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"Batch generation (Attempt {attempt+1}/{max_attempts})..."})
                
                if attempt == 0 or last_response is None:
                    response = await client.generate(prompt, json_mode=True)
                else:
                    # On retry, ask LLM to fix its own broken JSON instead of regenerating
                    fix_prompt = f"""Your previous response was not valid JSON. 
The error was: {last_error}

Here is the broken response (first 2000 chars):
{last_response[:2000]}

Please return the SAME content but as VALID JSON. Rules:
- All string values must have properly escaped quotes (use \\")
- All string values must have properly escaped newlines (use \\n)
- No trailing commas before }} or ]]
- Return ONLY the JSON object, no markdown
"""
                    response = await client.generate(fix_prompt, json_mode=True)
                
                last_response = response
                
                # Try parsing with recovery pipeline
                files_dict, parse_error = self._parse_json_robust(response)
                
                if files_dict is not None:
                    # Extract Signature
                    signature = None
                    if "__thought_signature__" in files_dict:
                        sig_data = files_dict.pop("__thought_signature__")
                        from app.agents.state import ThoughtSignature
                        from datetime import datetime
                        import uuid
                        
                        signature = ThoughtSignature(
                            signature_id=f"sig_virtuoso_{uuid.uuid4().hex[:8]}",
                            agent="VIRTUOSO",
                            step_id=None,
                            timestamp=datetime.now().isoformat(),
                            intent=sig_data.get("intent", "Code Generation") if isinstance(sig_data, dict) else "Code Generation",
                            rationale=sig_data.get("rationale", "") if isinstance(sig_data, dict) else "",
                            confidence=float(sig_data.get("confidence", 0.8)) if isinstance(sig_data, dict) else 0.8,
                            alternatives_considered=sig_data.get("alternatives_considered", []) if isinstance(sig_data, dict) else [],
                            context_used=sig_data.get("context_used", []) if isinstance(sig_data, dict) else [],
                            predicted_outcome=sig_data.get("predicted_outcome", "") if isinstance(sig_data, dict) else "",
                            token_usage=len(response) // 4,
                            model_used="gemini-2.0-flash-exp"
                        )
                    
                    # VALIDATION: Check content of generated .json files
                    for path, content in list(files_dict.items()):
                        if path.endswith(".json") and isinstance(content, str):
                            try:
                                json.loads(content, strict=False)
                            except json.JSONDecodeError:
                                fixed_content = re.sub(r',\s*([}\]])', r'\1', content)
                                try:
                                    json.loads(fixed_content, strict=False)
                                    files_dict[path] = fixed_content
                                except:
                                    files_dict[path] = "{}"
                    
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"✅ Generated {len(files_dict)} files in batch"})
                    
                    # POST-GENERATION: Validate cross-references
                    # Catches imports to files that weren't generated (e.g., '../styles/globals.css')
                    files_dict = self._validate_cross_references(files_dict)
                    if len(files_dict) > len(file_list): # Check if new files were added by cross-ref validation
                        new_count = len(files_dict) - len(file_list)
                        if new_count > 0:
                            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  📎 Cross-ref validation: auto-created {new_count} missing referenced files"})
                    
                    # POST-GENERATION: Validate required files (bin scripts, etc)
                    files_dict = self._validate_required_files(files_dict, profile)

                    return {"files": files_dict, "signature": signature}
                
                else:
                    last_error = parse_error
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ JSON parse error: {str(parse_error)[:80]}"})
                    await asyncio.sleep(1)
                    continue
                    
            except Exception as e:
                error_str = str(e)
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Error: {error_str[:50]}..."})
                last_error = error_str
                
                if "Ollama not available" in error_str:
                    break
                    
                await asyncio.sleep(1)
                continue
        
        # Fallback: Sequential generation
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ Batch failed. Using sequential generation..."})
        return await self.sequential_generate_files(file_list, context, existing_files)

    def _parse_json_robust(self, raw: str):
        """
        Multi-stage JSON recovery pipeline.
        Returns (dict, None) on success or (None, error_string) on failure.
        
        Delegates to shared safe_parse_json for stages 1-3, then falls back
        to regex extraction for Virtuoso-specific recovery.
        """
        from app.core.schema_validator import safe_parse_json
        
        # Stages 1-3: shared parser (direct, strip fences, fix commas)
        result, error = safe_parse_json(raw)
        if result is not None:
            return result, None
        
        # Stage 4: Regex extraction — find all "filepath": "content" pairs
        # This handles cases where JSON is structurally broken but content is there
        cleaned = raw.strip()
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
        
        try:
            files = {}
            pattern = r'"([^"]+\.[a-zA-Z]{1,5})":\s*"((?:[^"\\]|\\.)*)(?:"|$)'
            matches = re.finditer(pattern, cleaned, re.DOTALL)
            
            for m in matches:
                filepath = m.group(1)
                content = m.group(2)
                try:
                    content = content.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
                except:
                    pass
                files[filepath] = content
            
            if len(files) >= 2:
                logger.info(f"_parse_json_robust: Recovered {len(files)} files via regex extraction")
                return files, None
        except Exception:
            pass
        
        return None, error

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
            
            # Get stack-aware rules for sequential generation
            from app.core.stack_profiles import detect_stack
            seq_profile = detect_stack("", context.split("Stack:")[1].strip().split("\n")[0].strip() if "Stack:" in context else "auto")
            seq_rules = seq_profile.get_virtuoso_rules_text()
            
            prompt = f"""
Generate production code for: {path}
Description: {desc}
Context: {context}

Return ONLY the code, no markdown blocks.

RULES ({seq_profile.display_name}):
{seq_rules if seq_rules else "Write clean, production-ready code."}
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
                    
                    # If path looks like a URL path (starts with /), map to project file
                    if path.startswith("/"):
                        url_path = path.lstrip("/")
                        # Try common project locations for static/served files
                        candidates = [
                            f"frontend/public/{url_path}",
                            f"frontend/src/{url_path}",
                            f"frontend/{url_path}",
                            f"frontend/views/{url_path}",
                            url_path,
                        ]
                        found = False
                        for candidate in candidates:
                            if candidate in existing_files:
                                files_to_fix[candidate] = instruction
                                found = True
                                break
                        if not found:
                            # File doesn't exist → the server.js routing/static config is wrong
                            for server_file in _server_config_candidates(existing_files):
                                existing_instruction = files_to_fix.get(server_file, "")
                                combined = f"{existing_instruction}; Also fix: {url_path} returns 404" if existing_instruction else f"Fix routing: {url_path} returns 404. Check static file serving path and ensure files are served from the correct directory."
                                files_to_fix[server_file] = combined
                                break
                    else:
                        if path.startswith("./"):
                            path = path[2:]
                        files_to_fix[path] = instruction
                else:
                    # Fallback: fuzzy match against existing files
                    matched = False
                    for existing_path in existing_files.keys():
                        if existing_path in item or existing_path.split("/")[-1] in item:
                            files_to_fix[existing_path] = f"Fix error: {item}"
                            matched = True
                    
                    # If still no match and it's a 404/routing error, target server.js
                    if not matched and ("404" in item or "Not Found" in item):
                        for server_file in _server_config_candidates(existing_files):
                            existing_instruction = files_to_fix.get(server_file, "")
                            combined = f"{existing_instruction}; {item}" if existing_instruction else f"Fix routing issue: {item}"
                            files_to_fix[server_file] = combined
                            break
                            
        if not files_to_fix:
             await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ Could not identify specific files to fix. Targeting server config files..."})
             # Instead of regenerating everything, target the most likely culprits
             for pf in _server_config_candidates(existing_files, include_package=True):
                 files_to_fix[pf] = f"Fix errors: {'; '.join(str(e)[:100] for e in errors[:5])}"
             if not files_to_fix:
                 # Last resort: regenerate
                 return await self.sequential_generate_files([{"path": p} for p in existing_files], f"Fix errors: {errors}")

        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔧 Patching {len(files_to_fix)} files: {list(files_to_fix.keys())}"})
        
        repaired_files = existing_files.copy()
        changed_files = []  # Track what we changed for cascade detection
        
        for path, instruction in files_to_fix.items():
            original_code = existing_files.get(path, "")
            
            # Get stack-aware repair rules
            from app.core.stack_profiles import detect_stack
            repair_profile = detect_stack("", "auto")
            repair_rules = repair_profile.get_virtuoso_rules_text()
            
            # --- SURGICAL PATCH PROMPT ---
            # Ask LLM for specific changes, not full file rewrite
            prompt = f"""
SURGICAL FIX — Return ONLY the specific changes needed.

TARGET FILE: {path}
ERROR TO FIX: {instruction}

CURRENT CODE:
```
{original_code}
```

YOUR TASK:
Identify the EXACT lines causing the error and provide ONLY the fix.
Return your fix as SEARCH/REPLACE blocks. Each block finds exact text in the file 
and replaces it with the corrected version.

FORMAT (use this EXACTLY):
<<<<<<< SEARCH
exact lines to find in the current code
=======
replacement lines
>>>>>>> REPLACE

RULES:
1. The SEARCH section MUST match the current code EXACTLY (including whitespace/indentation).
2. Keep changes MINIMAL — fix ONLY what's broken. Do NOT rewrite unrelated code.
3. You may provide MULTIPLE SEARCH/REPLACE blocks if the fix requires changes in multiple places.
4. If the entire file needs restructuring (e.g., wrong static path), you may provide a larger block.
5. Preserve all existing functionality that is not related to the error.
{repair_rules if repair_rules else ''}
"""
            try:
                patch_response = await client.generate(prompt)
                # Clean markdown wrappers
                patch_response = patch_response.replace("```diff", "").replace("```", "").strip()
                
                # Apply patches
                patched_code = self._apply_patches(original_code, patch_response, path)
                
                if patched_code != original_code:
                    repaired_files[path] = patched_code
                    changed_files.append(path)
                    await sm.emit("file_generated", {"path": path, "content": patched_code, "status": "patched"})
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  ✅ Patched {path}"})
                else:
                    # Patch didn't match — fall back to full fix for THIS file only
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  ⚠️ Patch didn't apply for {path}, using full fix..."})
                    full_code = await self._full_fix_single_file(client, path, original_code, instruction, repair_rules)
                    if full_code and full_code != original_code:
                        repaired_files[path] = full_code
                        changed_files.append(path)
                        await sm.emit("file_generated", {"path": path, "content": full_code, "status": "repaired"})
                
                # OPTIMIZATION: Validate JSON immediately if fixing a JSON file
                if path.endswith(".json") and path in repaired_files:
                    try:
                        json.loads(repaired_files[path], strict=False)
                    except json.JSONDecodeError:
                        try:
                            match = re.search(r"(\{.*\})", repaired_files[path], re.DOTALL)
                            if match:
                                san_code = match.group(1)
                                json.loads(san_code, strict=False)
                                repaired_files[path] = san_code
                            else:
                                raise ValueError("Generated code is not valid JSON")
                        except Exception:
                            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Generated invalid JSON for {path}. Keeping original."})
                            repaired_files[path] = original_code  # Revert
                            if path in changed_files:
                                changed_files.remove(path)
                            
            except Exception as e:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"Failed to patch {path}: {e}"})
        
        # --- CASCADE DETECTION ---
        # After fixing files, check if any other files depend on the changed files
        if changed_files:
            cascade_files = self._find_cascade_files(changed_files, repaired_files)
            if cascade_files:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔗 Cascade: {len(cascade_files)} dependent files may need updates: {cascade_files}"})
                for cascade_path in cascade_files:
                    if cascade_path in repaired_files and cascade_path not in changed_files:
                        try:
                            cascade_code = await self._fix_cascade_file(
                                client, cascade_path, repaired_files[cascade_path],
                                changed_files, repaired_files
                            )
                            if cascade_code and cascade_code != repaired_files[cascade_path]:
                                repaired_files[cascade_path] = cascade_code
                                await sm.emit("file_generated", {"path": cascade_path, "content": cascade_code, "status": "cascade_fix"})
                                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  🔗 Cascade-fixed {cascade_path}"})
                        except Exception as cas_err:
                            logger.warning(f"Cascade fix failed for {cascade_path}: {cas_err}")
                
        return repaired_files
    
    def _apply_patches(self, original: str, patch_text: str, filepath: str) -> str:
        """
        Apply SEARCH/REPLACE patch blocks to the original code.
        Returns the patched code, or the original if no patches matched.
        """
        # Parse SEARCH/REPLACE blocks
        blocks = re.findall(
            r'<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>> REPLACE',
            patch_text,
            re.DOTALL
        )
        
        if not blocks:
            # Also try without the exact markers (some LLMs use variations)
            blocks = re.findall(
                r'<<<+\s*SEARCH\s*\n(.*?)\n===+\n(.*?)\n>>>+\s*REPLACE',
                patch_text,
                re.DOTALL
            )
        
        if not blocks:
            logger.debug(f"No SEARCH/REPLACE blocks found in patch for {filepath}")
            return original
        
        result = original
        applied = 0
        
        for search, replace in blocks:
            search = search.strip('\r')
            replace = replace.strip('\r')
            
            if search in result:
                result = result.replace(search, replace, 1)
                applied += 1
            else:
                # Try with normalized whitespace (LLM might slightly differ)
                search_stripped = '\n'.join(line.rstrip() for line in search.split('\n'))
                result_stripped = '\n'.join(line.rstrip() for line in result.split('\n'))
                if search_stripped in result_stripped:
                    # Apply on the stripped version, then use it
                    result = result_stripped.replace(search_stripped, replace, 1)
                    applied += 1
                else:
                    logger.debug(f"Patch block didn't match for {filepath}: {search[:80]}...")
        
        if applied > 0:
            logger.info(f"Applied {applied}/{len(blocks)} patch blocks to {filepath}")
            return result
        
        return original  # No patches applied
    
    async def _full_fix_single_file(self, client, path: str, original_code: str, instruction: str, repair_rules: str) -> str:
        """
        Fallback: Full file regeneration for a single file when surgical patching fails.
        Still targeted — only regenerates ONE file, not the whole project.
        """
        prompt = f"""
FIX THIS FILE. Return the COMPLETE fixed code.

TARGET: {path}
ERROR: {instruction}

CURRENT CODE:
{original_code}

TASK: Fix the error while keeping all existing functionality intact.
Return ONLY the fixed code, no explanations.
{repair_rules if repair_rules else ''}
"""
        new_code = await client.generate(prompt)
        # Clean markdown
        new_code = new_code.replace("```python", "").replace("```typescript", "").replace("```javascript", "").replace("```js", "").replace("```ts", "")
        new_code = new_code.replace("```tsx", "").replace("```json", "").replace("```", "").strip()
        
        # Remove bare language identifiers at start
        for lang in ["javascript", "typescript", "python", "json", "tsx", "jsx", "js", "ts"]:
            if re.match(f"^{lang}\\s+", new_code, re.IGNORECASE):
                new_code = re.sub(f"^{lang}\\s+", "", new_code, flags=re.IGNORECASE).strip()
        
        return new_code
    
    def _find_cascade_files(self, changed_files: list, all_files: dict) -> list:
        """
        Find files that depend on the changed files and may need updates.
        
        Detects:
        - import/require references to changed files
        - HTML <script>/<link> references
        - Config files that reference changed paths
        """
        cascade = []
        
        # Build lookup: filename -> full path for changed files
        changed_basenames = {}
        for cf in changed_files:
            basename = cf.split("/")[-1]
            name_no_ext = basename.rsplit(".", 1)[0] if "." in basename else basename
            changed_basenames[basename] = cf
            changed_basenames[name_no_ext] = cf
        
        for path, content in all_files.items():
            if path in changed_files:
                continue  # Don't cascade to self
            
            # Check if this file references any changed file
            for ref_name, changed_path in changed_basenames.items():
                # Common reference patterns
                patterns = [
                    f"require('{ref_name}",      # Node.js require
                    f'require("{ref_name}',
                    f"from '{ref_name}",          # ES import
                    f'from "{ref_name}',
                    f"import '{ref_name}",
                    f'import "{ref_name}',
                    f'src="{ref_name}',           # HTML script/img src
                    f"src='{ref_name}",
                    f'href="{ref_name}',          # HTML link href
                    f"href='{ref_name}",
                    f"/{ref_name}",               # URL path reference
                ]
                if any(p in content for p in patterns):
                    cascade.append(path)
                    break
        
        return cascade[:5]  # Limit cascade to 5 files
    
    async def _fix_cascade_file(self, client, path: str, content: str, changed_files: list, all_files: dict) -> str:
        """
        Fix a file that depends on changed files. Only apply necessary updates.
        """
        # Build context of what changed
        changes_summary = []
        for cf in changed_files:
            old_snippet = ""  # We don't have the old content easily
            new_content = all_files.get(cf, "")
            changes_summary.append(f"CHANGED FILE: {cf}\nNEW CONTENT (first 500 chars):\n{new_content[:500]}")
        
        prompt = f"""
CASCADE FIX — A dependency of this file was modified. Check if this file needs updates.

THIS FILE: {path}
```
{content}
```

THE FOLLOWING FILES WERE JUST FIXED:
{chr(10).join(changes_summary)}

YOUR TASK:
1. Check if {path} needs any changes due to the fixes above (e.g., updated paths, changed exports, renamed functions).
2. If YES, return SEARCH/REPLACE blocks with ONLY the specific changes.
3. If NO changes needed, return exactly: NO_CHANGES_NEEDED

FORMAT for changes:
<<<<<<< SEARCH
exact lines to find
=======
replacement lines
>>>>>>> REPLACE
"""
        response = await client.generate(prompt)
        response = response.strip()
        
        if "NO_CHANGES_NEEDED" in response:
            return content  # No changes
        
        # Apply patches
        patched = self._apply_patches(content, response, path)
        return patched

    # --- Strategy-Specific Repair Methods ---
    # Used by DiagnosticianAgent's strategy dispatch in orchestrator

    async def repair_files_targeted(
        self,
        current_files: dict,
        affected_files: list,
        fix_suggestions: list
    ) -> dict:
        """
        Perform targeted surgical fixes on specific files.
        Uses SEARCH/REPLACE patches, not full file regeneration.
        
        Key: When affected_files contains non-existent paths (e.g., image 404s),
        resolves them to the code files that REFERENCE those paths.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        fixes_prompt = "\n".join(f"- {s}" for s in fix_suggestions)
        
        if not affected_files and not fix_suggestions:
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ No affected files or suggestions. Nothing to fix."})
            return current_files
        
        # --- RESOLVE affected_files: map non-existent paths to actual code files ---
        resolved_files = []
        missing_asset_instructions = {}  # path -> instruction about what's missing
        
        for af in affected_files[:8]:
            if af in current_files:
                resolved_files.append(af)
            else:
                # This file doesn't exist in the project — it's a missing asset (e.g., /images/tshirt.jpg)
                # Find which CODE files reference this missing asset and patch THOSE
                asset_name = af.split("/")[-1] if "/" in af else af
                url_path = af.lstrip("/") if af.startswith("/") else af
                
                # Search all project files for references to this missing asset
                referencing_files = []
                for path, content in current_files.items():
                    if asset_name in content or url_path in content or af in content:
                        referencing_files.append(path)
                
                if referencing_files:
                    for rf in referencing_files[:3]:  # Limit per asset
                        if rf not in resolved_files:
                            resolved_files.append(rf)
                        # Accumulate instructions per file
                        existing = missing_asset_instructions.get(rf, "")
                        new_instr = f"Asset '{af}' is missing (404). Replace its reference with a working placeholder URL (e.g., https://placehold.co/300x300?text={asset_name.split('.')[0]})"
                        missing_asset_instructions[rf] = f"{existing}; {new_instr}" if existing else new_instr
                    
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  📎 Missing asset '{af}' → patching {referencing_files[:3]}"})
                else:
                    # No file references it — try common server/config files
                    for fallback in _server_config_candidates(current_files):
                        if fallback not in resolved_files:
                            resolved_files.append(fallback)
                            missing_asset_instructions[fallback] = missing_asset_instructions.get(fallback, "") + f"; Fix: '{af}' returns 404"
                            break
        
        if not resolved_files:
            # Still nothing — fall back to repair_files which has broader matching
            await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": "⚠️ Could not resolve affected files. Falling back to error-based repair..."})
            return await self.repair_files(current_files, fix_suggestions)
        
        files_to_fix = resolved_files[:5]
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔧 Targeted fix on {len(files_to_fix)} files: {files_to_fix}"})
        
        result = current_files.copy()
        changed_files = []
        
        for path in files_to_fix:
            if path not in current_files:
                continue
                
            original = current_files[path]
            
            # Build file-specific instructions
            file_specific_instructions = ""
            if path in missing_asset_instructions:
                file_specific_instructions = f"\n\nSPECIFIC MISSING ASSET FIXES FOR THIS FILE:\n{missing_asset_instructions[path]}"
            
            prompt = f"""
SURGICAL FIX — Return ONLY the specific changes needed.

TARGET FILE: {path}
ISSUES TO FIX:
{fixes_prompt}
{file_specific_instructions}

CURRENT CODE:
```
{original}
```

YOUR TASK:
Fix ONLY the issues listed. Return SEARCH/REPLACE blocks for the exact changes.
Do NOT rewrite the entire file. Change the MINIMUM necessary.

FORMAT:
<<<<<<< SEARCH
exact lines to find in the current code
=======
replacement lines
>>>>>>> REPLACE

If no change is needed for this file, return: NO_CHANGES_NEEDED
"""
            try:
                response = await client.generate(prompt)
                response = response.replace("```diff", "").replace("```", "").strip()
                
                if "NO_CHANGES_NEEDED" in response:
                    continue
                
                patched = self._apply_patches(original, response, path)
                
                if patched != original:
                    result[path] = patched
                    changed_files.append(path)
                    await sm.emit("file_generated", {"path": path, "content": patched, "status": "patched"})
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  ✅ Surgical fix applied to {path}"})
                else:
                    # Fallback: full fix for this one file
                    await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  ⚠️ Patch didn't apply for {path}, using full fix..."})
                    from app.core.stack_profiles import detect_stack
                    repair_profile = detect_stack("", "auto")
                    repair_rules = repair_profile.get_virtuoso_rules_text()
                    full_code = await self._full_fix_single_file(client, path, original, fixes_prompt, repair_rules)
                    if full_code and full_code != original:
                        result[path] = full_code
                        changed_files.append(path)
                        await sm.emit("file_generated", {"path": path, "content": full_code, "status": "repaired"})
                    
            except Exception as e:
                await sm.emit("agent_log", {
                    "agent_name": "VIRTUOSO",
                    "message": f"⚠️ Fix failed for {path}: {str(e)[:60]}"
                })
        
        # --- CASCADE DETECTION ---
        if changed_files:
            cascade_files = self._find_cascade_files(changed_files, result)
            if cascade_files:
                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔗 Cascade: checking {len(cascade_files)} dependent files"})
                for cascade_path in cascade_files:
                    if cascade_path in result and cascade_path not in changed_files:
                        try:
                            cascade_code = await self._fix_cascade_file(
                                client, cascade_path, result[cascade_path],
                                changed_files, result
                            )
                            if cascade_code and cascade_code != result[cascade_path]:
                                result[cascade_path] = cascade_code
                                await sm.emit("file_generated", {"path": cascade_path, "content": cascade_code, "status": "cascade_fix"})
                                await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"  🔗 Cascade-fixed {cascade_path}"})
                        except Exception as cas_err:
                            logger.warning(f"Cascade fix failed for {cascade_path}: {cas_err}")
        
        if changed_files:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"✅ Targeted fixes applied to {len(changed_files)} files"
            })
        else:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": "⚠️ No patches applied. Files may already be correct or errors unclear."
            })
        
        return result

    async def rewrite_files(
        self,
        current_files: dict,
        affected_files: list,
        root_cause: str
    ) -> dict:
        """
        Completely regenerate specific files from scratch.
        Used when files have major logic issues not fixable by patching.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        files_to_rewrite = affected_files[:3]
        
        if not files_to_rewrite:
            return await self.repair_files(current_files, [root_cause])
        
        # Provide context from OTHER files so rewrite is consistent
        context_files = {k: v for k, v in current_files.items() if k not in files_to_rewrite}
        context_summary = "\n".join(
            f"- {path} ({len(content)} chars)" for path, content in list(context_files.items())[:10]
        )
        
        prompt = f"""
You are regenerating files from scratch due to major issues.

**ROOT CAUSE:** {root_cause}

**FILES TO REGENERATE:** {json.dumps(files_to_rewrite)}

**OTHER PROJECT FILES (for context):**
{context_summary}

**YOUR TASK:**
Write complete, correct implementations for the files listed above.
The new code must integrate with the rest of the project.

Return JSON:
{{
  "file1.py": "complete new content",
  "file2.js": "complete new content"
}}
"""
        
        try:
            response = await client.generate(prompt, json_mode=True)
            cleaned = response.replace("```json", "").replace("```", "").strip()
            rewritten = json.loads(cleaned, strict=False)
            
            # VALIDATION: Check content of generated .json files
            for path, content in rewritten.items():
                if path.endswith(".json") and isinstance(content, str):
                    try:
                        json.loads(content, strict=False)
                    except json.JSONDecodeError as e:
                        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Invalid JSON content in {path} (rewrite): {e}"})
                        import re
                        fixed_content = re.sub(r',\s*([}\]])', r'\1', content)
                        try:
                            json.loads(fixed_content, strict=False)
                            rewritten[path] = fixed_content
                        except:
                            rewritten[path] = "{}"
            
            result = current_files.copy()
            result.update(rewritten)
            
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"✅ Rewrote {len(rewritten)} files from scratch"
            })
            
            return result
            
        except Exception as e:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"⚠️ Rewrite failed: {str(e)[:60]}. Falling back..."
            })
            return await self.repair_files(current_files, [root_cause])

    async def add_missing_dependencies(
        self,
        current_files: dict,
        errors: list
    ) -> dict:
        """
        Add missing imports or dependencies to fix import/module errors.
        Focuses on package.json, requirements.txt, and import statements.
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        error_summary = "\n".join(f"- {e[:150]}" for e in errors[:5])
        
        # Include current config files for context
        config_files = {}
        for path in ["package.json", "requirements.txt", "tsconfig.json"]:
            if path in current_files:
                config_files[path] = current_files[path]
        
        config_content = "\n".join(
            f"--- {p} ---\n{c[:500]}\n" for p, c in config_files.items()
        ) if config_files else "No config files found."
        
        prompt = f"""
You are fixing import/dependency errors.

**ERRORS:**
{error_summary}

**CURRENT CONFIG FILES:**
{config_content}

**YOUR TASK:**
1. Identify missing imports or dependencies
2. Update relevant files to add them
3. Return ONLY the files that need changes

Return JSON:
{{
  "package.json": "updated content with missing deps",
  "src/app.js": "updated content with correct imports"
}}
"""
        
        try:
            response = await client.generate(prompt, json_mode=True)
            cleaned = response.replace("```json", "").replace("```", "").strip()
            fixes = json.loads(cleaned, strict=False)
            
            # VALIDATION: Check content of generated .json files
            for path, content in fixes.items():
                if path.endswith(".json") and isinstance(content, str):
                    try:
                        json.loads(content, strict=False)
                    except json.JSONDecodeError as e:
                        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Invalid JSON content in {path} (deps): {e}"})
                        import re
                        fixed_content = re.sub(r',\s*([}\]])', r'\1', content)
                        try:
                            json.loads(fixed_content, strict=False)
                            fixes[path] = fixed_content
                        except:
                            fixes[path] = "{}"
            
            result = current_files.copy()
            result.update(fixes)
            
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"✅ Added missing dependencies in {len(fixes)} files"
            })
            
            return result
            
        except Exception as e:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"⚠️ Dependency fix failed: {str(e)[:60]}. Falling back..."
            })
            return await self.repair_files(current_files, errors)

    async def fix_configuration(
        self,
        current_files: dict,
        root_cause: str
    ) -> dict:
        """
        Fix configuration files only (package.json, tsconfig, vite.config, etc.).
        """
        from app.core.local_model import HybridModelClient
        from app.core.socket_manager import SocketManager
        
        client = HybridModelClient()
        sm = SocketManager()
        
        # Identify config files
        config_patterns = [
            "package.json", "tsconfig.json", "tsconfig.app.json",
            "vite.config", "next.config", "tailwind.config",
            "postcss.config", ".eslintrc", "webpack.config",
            "requirements.txt", "pyproject.toml"
        ]
        config_files = {}
        for path, content in current_files.items():
            basename = path.split("/")[-1].split("\\")[-1]
            if any(pat in basename for pat in config_patterns):
                config_files[path] = content
        
        if not config_files:
            return await self.repair_files(current_files, [root_cause])
        
        config_content = "\n".join(
            f"--- {p} ---\n{c}\n" for p, c in config_files.items()
        )
        
        prompt = f"""
You are fixing configuration issues in a project.

**ROOT CAUSE:** {root_cause}

**CURRENT CONFIG FILES:**
{config_content}

**YOUR TASK:**
Fix ONLY the configuration files to resolve the root cause.
Do not modify source code files.

Return JSON with fixed config files:
{{
  "package.json": "fixed content",
  "tsconfig.json": "fixed content"
}}
"""
        
        try:
            response = await client.generate(prompt, json_mode=True)
            cleaned = response.replace("```json", "").replace("```", "").strip()
            fixes = json.loads(cleaned, strict=False)
            
            # VALIDATION: Check content of generated .json files
            for path, content in fixes.items():
                if path.endswith(".json") and isinstance(content, str):
                    try:
                        json.loads(content, strict=False)
                    except json.JSONDecodeError as e:
                        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"⚠️ Invalid JSON content in {path} (config): {e}"})
                        import re
                        fixed_content = re.sub(r',\s*([}\]])', r'\1', content)
                        try:
                            json.loads(fixed_content, strict=False)
                            fixes[path] = fixed_content
                        except:
                            fixes[path] = "{}"
            
            result = current_files.copy()
            result.update(fixes)
            
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"✅ Fixed {len(fixes)} config files"
            })
            
            return result
            
        except Exception as e:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"⚠️ Config fix failed: {str(e)[:60]}. Falling back..."
            })
            return await self.repair_files(current_files, [root_cause])

    def _format_files_for_prompt(self, files: dict, specific_files: list) -> str:
        """Format specific files for prompt inclusion (truncated to avoid token overflow)."""
        formatted = []
        for path in specific_files:
            if path in files:
                content = files[path][:1500]  # First 1500 chars
                truncated = " (truncated)" if len(files[path]) > 1500 else ""
                formatted.append(f"\n--- {path}{truncated} ---\n{content}\n")
        return "".join(formatted) if formatted else "No matching files found."

    def _sanitize_for_profile(self, files: dict, profile) -> tuple:
        """
        Remove files that are forbidden by the stack profile.
        For static-html: strips package.json, tailwind configs, postcss configs, etc.
        Returns (cleaned_files, list_of_removed_filenames).
        """
        if profile.id != "static-html":
            return files, []
        
        # Files that should NEVER exist in a static HTML project
        forbidden_patterns = [
            "package.json", "package-lock.json", "node_modules",
            "tailwind.config", "postcss.config", "tsconfig.json",
            "webpack.config", "vite.config", "rollup.config",
            ".babelrc", "babel.config", "next.config",
            "angular.json", "nuxt.config",
        ]
        
        cleaned = {}
        removed = []
        
        for path, content in files.items():
            basename = path.split("/")[-1].split("\\")[-1]
            if any(basename.startswith(fp) or basename == fp for fp in forbidden_patterns):
                removed.append(basename)
                logger.info(f"Sanitizer: Removed forbidden file '{path}' from static-html project")
            else:
                cleaned[path] = content
        
        return cleaned, removed

    def _normalize_file_paths(self, files: dict) -> dict:
        """
        Normalize all file paths in the generated files dict:
        1. Convert backslashes to forward slashes
        2. Strip leading/trailing slashes and ./
        3. Deduplicate paths (last-write-wins)
        4. Skip metadata keys (starting with __)
        
        This is the primary defense against duplicate folder generation where
        the LLM returns both 'frontend\\src\\app\\page.tsx' and 'frontend/src/app/page.tsx'.
        """
        normalized = {}
        dedup_log = []
        
        for path, content in files.items():
            # Normalize separators
            clean = path.strip().replace("\\", "/").strip("/")
            # Collapse consecutive slashes (e.g. frontend//src → frontend/src)
            clean = re.sub(r'/+', '/', clean)
            if clean.startswith("./"):
                clean = clean[2:]
            
            # Skip empty paths or metadata keys
            if not clean or clean.startswith("__"):
                continue
            
            # Track deduplication
            if clean in normalized and clean != path:
                dedup_log.append(f"  Dedup: '{path}' overwrites existing entry for '{clean}'")
            
            normalized[clean] = content
        
        if dedup_log:
            logger.info(f"Virtuoso._normalize_file_paths: Resolved {len(dedup_log)} path collisions")
            for log_entry in dedup_log:
                logger.debug(log_entry)
        
        return normalized

    def _validate_cross_references(self, files: dict) -> dict:
        """
        Post-generation validator: scan all generated files for imports/requires
        that reference files NOT in the generated set. Auto-create missing files.
        
        This catches the common LLM failure where it generates code like:
            import '../styles/globals.css'   # but styles/globals.css was never generated
            imageUrl: '/images/tshirt.jpg'   # but the image doesn't exist
        
        Strategy:
        1. Extract all import/require paths from each file
        2. Resolve relative paths against the file's directory
        3. For each reference that doesn't match a generated file:
           a. CSS → create with Tailwind/basic global styles
           b. JS/TS → create empty export stub
           c. Image/asset URL → rewrite reference to use placeholder URL
        """
        import posixpath
        
        created_files = {}
        patched_files = {}
        
        for filepath, content in files.items():
            if not isinstance(content, str):
                continue
            
            file_dir = posixpath.dirname(filepath)
            
            # Extract import/require references
            import_patterns = [
                # ES import: import X from './path'  or  import './path'
                re.compile(r"""import\s+(?:.*?\s+from\s+)?['"]([^'"]+)['"]"""),
                # require: require('./path')
                re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
            ]
            
            for pattern in import_patterns:
                for match in pattern.finditer(content):
                    ref_path = match.group(1)
                    
                    # Skip node_modules/external packages
                    if not ref_path.startswith('.') and not ref_path.startswith('/'):
                        continue
                    
                    # Resolve relative path
                    if ref_path.startswith('.'):
                        resolved = posixpath.normpath(posixpath.join(file_dir, ref_path))
                    else:
                        resolved = ref_path.lstrip('/')
                    
                    # Check if the resolved file exists (with common extensions)
                    extensions_to_try = ['']
                    if '.' not in posixpath.basename(resolved):
                        # No extension → try common ones
                        extensions_to_try = ['.js', '.jsx', '.ts', '.tsx', '.mjs', '/index.js', '/index.ts', '/index.tsx']
                    
                    found = False
                    for ext in extensions_to_try:
                        candidate = resolved + ext
                        if candidate in files or candidate in created_files:
                            found = True
                            break
                    
                    if not found:
                        # Missing reference! Create the file with sensible defaults
                        actual_path = resolved
                        if '.' not in posixpath.basename(resolved):
                            # Default to .js/.ts based on project
                            has_ts = any(p.endswith('.ts') or p.endswith('.tsx') for p in files)
                            actual_path = resolved + ('.ts' if has_ts else '.js')
                        
                        if actual_path.endswith('.css'):
                            # Create CSS with Tailwind defaults or basic globals
                            created_files[actual_path] = """@tailwind base;
@tailwind components;
@tailwind utilities;

/* Global styles */
:root {
  --foreground-rgb: 0, 0, 0;
  --background-rgb: 255, 255, 255;
}

body {
  color: rgb(var(--foreground-rgb));
  background: rgb(var(--background-rgb));
  margin: 0;
  padding: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

* {
  box-sizing: border-box;
  padding: 0;
  margin: 0;
}
"""
                            logger.info(f"CrossRef: Created missing CSS '{actual_path}' (referenced by '{filepath}')")
                        
                        elif actual_path.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs')):
                            created_files[actual_path] = "// Auto-generated stub\nexport default {};\n"
                            logger.info(f"CrossRef: Created missing JS/TS stub '{actual_path}' (referenced by '{filepath}')")
                        
                        else:
                            logger.warning(f"CrossRef: Unknown type for missing file '{actual_path}' (referenced by '{filepath}')")
            
            # Check for image URL references in data/config files (server.js, etc.)
            # Pattern: '/images/something.jpg' or '/assets/something.png'
            asset_refs = re.findall(r"""['"]/(images|assets|img|static)/([^'"]+)['"]""", content)
            if asset_refs:
                # These are typically server-side data references to static assets
                # Replace with placeholder URLs
                modified_content = content
                for folder, asset_name in asset_refs:
                    old_ref = f"/{folder}/{asset_name}"
                    # Get clean name for the placeholder
                    clean_name = asset_name.rsplit('.', 1)[0] if '.' in asset_name else asset_name
                    clean_name = clean_name.replace('-', '+').replace('_', '+')
                    placeholder = f"https://placehold.co/400x300?text={clean_name}"
                    modified_content = modified_content.replace(f"'{old_ref}'", f"'{placeholder}'")
                    modified_content = modified_content.replace(f'"{old_ref}"', f'"{placeholder}"')
                    logger.info(f"CrossRef: Replaced missing asset '{old_ref}' with placeholder in '{filepath}'")
                
                if modified_content != content:
                    patched_files[filepath] = modified_content
        
        # Apply patches and additions
        result = dict(files)
        result.update(patched_files)
        result.update(created_files)
        
        total_fixes = len(created_files) + len(patched_files)
        if total_fixes > 0:
            logger.info(f"CrossRef validation: created {len(created_files)} files, patched {len(patched_files)} files")
        
        return result

    def _extract_affected_files(self, errors: list, existing_files: dict) -> list:
        """
        Intelligently extract file paths from error messages.
        
        Handles:
        - Structured error dicts: {"file": "path", "issue": "...", "fix": "..."}
        - Raw string errors with file paths mentioned
        - URL paths from 404 errors (maps to project files)
        - Fuzzy matching against existing file paths
        
        Returns a deduplicated list of file paths that need repair.
        """
        affected = set()
        
        for error in errors:
            # Case 1: Structured error dict (from Sentinel, Tester, etc.)
            if isinstance(error, dict):
                if "file" in error:
                    path = error["file"].strip().replace("\\", "/").strip("/")
                    if path.startswith("./"):
                        path = path[2:]
                    affected.add(path)
                # Also check 'path' key
                if "path" in error:
                    path = error["path"].strip().replace("\\", "/").strip("/")
                    affected.add(path)
                continue
            
            # Case 2: Raw string error
            if isinstance(error, str):
                error_str = error
                
                # Pattern: "FILE: path - instruction" (from enriched playwright errors)
                match = re.search(r"FILE:\s*([^\s,]+)\s*-\s*(.*)", error_str, re.IGNORECASE)
                if match:
                    path = match.group(1).strip()
                    # URL path → project file mapping
                    if path.startswith("/"):
                        url_path = path.lstrip("/")
                        candidates = [
                            f"frontend/public/{url_path}",
                            f"frontend/src/{url_path}",
                            f"frontend/{url_path}",
                            f"frontend/views/{url_path}",
                            url_path,
                        ]
                        found = False
                        for candidate in candidates:
                            if candidate in existing_files:
                                affected.add(candidate)
                                found = True
                                break
                        if not found:
                            # 404 for missing resource → target server.js (routing/static config)
                            for sf in ["frontend/server.js", "frontend/index.js", "frontend/app.js"]:
                                if sf in existing_files:
                                    affected.add(sf)
                                    break
                    else:
                        affected.add(path.replace("\\", "/"))
                    continue
                
                # Pattern: "Error in path/to/file.ext"
                match = re.search(r"(?:Error|error|Failed|failed|Issue|issue)\s+(?:in|with|at)\s+([^\s:,]+\.\w+)", error_str)
                if match:
                    affected.add(match.group(1).strip().replace("\\", "/"))
                    continue
                
                # Fuzzy match: check if any existing file path appears in the error
                for existing_path in existing_files.keys():
                    norm_existing = existing_path.replace("\\", "/")
                    # Check full path or just filename
                    filename = norm_existing.split("/")[-1]
                    if norm_existing in error_str or filename in error_str:
                        affected.add(norm_existing)
                
                # 404/routing errors without file paths → target server.js
                if not affected and ("404" in error_str or "Not Found" in error_str):
                    for sf in ["frontend/server.js", "frontend/index.js", "frontend/app.js"]:
                        if sf in existing_files:
                            affected.add(sf)
                            break
        
        # Filter to only files that actually exist (or are close matches)
        validated = []
        normalized_existing = {p.replace("\\", "/"): p for p in existing_files.keys()}
        
        for path in affected:
            if path in normalized_existing:
                validated.append(path)
            else:
                # Try partial match (filename only)
                filename = path.split("/")[-1]
                for existing_norm, original in normalized_existing.items():
                    if existing_norm.endswith("/" + filename) or existing_norm == filename:
                        validated.append(existing_norm)
                        break
                else:
                    # File mentioned in error but doesn't exist yet — might need to be created
                    validated.append(path)
        
        return list(set(validated))

    def _validate_required_files(self, files: dict, profile: StackProfile) -> dict:
        """
        Validate that all required files exist. Auto-generate missing critical files.
        This prevents install_cmd failures due to missing files.
        """
        from app.core.socket_manager import SocketManager
        sm = SocketManager()
        
        missing_files = []
        auto_generated = {}
        
        # Check config_files from profile
        for required_path, description in profile.config_files.items():
            if required_path not in files:
                missing_files.append(required_path)
                
                # Auto-generate common missing files
                if required_path == "bin/rails":
                    auto_generated[required_path] = """#!/usr/bin/env ruby
APP_PATH = File.expand_path('../config/application', __dir__)
require_relative '../config/boot'
require 'rails/commands'
"""
                elif required_path == "bin/bundle":
                    auto_generated[required_path] = """#!/usr/bin/env ruby
ENV['BUNDLE_GEMFILE'] ||= File.expand_path('../Gemfile', __dir__)
require 'bundler/setup'
load Gem.bin_path('bundler', 'bundle')
"""
                elif required_path == "bin/setup":
                    auto_generated[required_path] = """#!/usr/bin/env ruby
require 'fileutils'
APP_ROOT = File.expand_path('..', __dir__)

def system!(*args)
  system(*args) || abort("\\n== Command #{args} failed ==")
end

FileUtils.chdir APP_ROOT do
  puts '== Installing dependencies =='
  system! 'gem install bundler --conservative'
  system('bundle check') || system!('bundle install')
end
"""
                elif required_path == "manage.py":
                    auto_generated[required_path] = """#!/usr/bin/env python
import os
import sys

if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)
"""
                elif required_path == "main.py":
                    auto_generated[required_path] = """if __name__ == "__main__":
    print("Hello from Python!")
"""
                elif required_path == "artisan":
                    auto_generated[required_path] = """#!/usr/bin/env php
<?php
define('LARAVEL_START', microtime(true));

require __DIR__.'/vendor/autoload.php';

$app = require_once __DIR__.'/bootstrap/app.php';

$kernel = $app->make(Illuminate\\Contracts\\Console\\Kernel::class);

$status = $kernel->handle(
    $input = new Symfony\\Component\\Console\\Input\\ArgvInput,
    $output = new Symfony\\Component\\Console\\Output\\ConsoleOutput
);

$kernel->terminate($input, $status);

exit($status);
"""
                elif required_path == "frontend/next.config.mjs":
                    auto_generated[required_path] = """/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
"""
                elif required_path == "frontend/vite.config.js":
                    auto_generated[required_path] = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
})
"""
                elif required_path == "frontend/index.html":
                    auto_generated[required_path] = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Vite App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""
                elif required_path.endswith("package.json"):
                    # Basic fallback package.json if completely missing
                    auto_generated[required_path] = """{
  "name": "app",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "react": "^18",
    "react-dom": "^18",
    "next": "14.1.0"
  }
}
"""
        
        if auto_generated:
            # Create a task for logging since we can't easily await in this sync/hybrid context or just to be safe
            import asyncio
            asyncio.create_task(sm.emit("agent_log", {
                "agent_name": "VIRTUOSO", 
                "message": f"🔧 Auto-generated {len(auto_generated)} missing critical files: {', '.join(auto_generated.keys())}"
            }))
            files.update(auto_generated)
        
        return files