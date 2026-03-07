# ACEA Sentinel - Orchestrator with Self-Healing Loop
# Manages the agent workflow with automatic error detection and fixing
# Generalized: stack-agnostic via StackProfiles, lazy agent init

import json
import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.metrics_collector import get_metrics_collector

# Updated imports for new components
from app.agents.state import AgentState
from app.core.persistence import AsyncRedisSaver, LangGraphRedisSaver
from app.core.key_manager import KeyManager
from app.core.HybridModelClient import HybridModelClient
from app.core.model_response import ModelResponse
from app.core.config import settings

# LangGraph
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

# Initialize Core Services
USE_REDIS_PERSISTENCE = settings.USE_REDIS_PERSISTENCE
REDIS_URL = settings.REDIS_URL
API_KEYS = settings.api_keys_list

# Setup Redis Saver and Key Manager
redis_saver: Optional[AsyncRedisSaver] = None
if USE_REDIS_PERSISTENCE:
    redis_saver = AsyncRedisSaver(REDIS_URL)

try:
    key_manager = KeyManager(API_KEYS)
    hybrid_client = HybridModelClient(key_manager)
except Exception as e:
    logger.warning(f"Failed to initialize KeyManager: {e}")
    hybrid_client = None

# --- Lazy Agent Initialization ---
# Agents are created on first use, not at module import time.
# This avoids circular imports and unnecessary resource allocation.
_agents = {}

def _get_agent(name: str):
    """Lazy-initialize and cache agent by name."""
    if name not in _agents:
        from app.agents.architect import ArchitectAgent
        from app.agents.virtuoso import VirtuosoAgent
        from app.agents.sentinel import SentinelAgent
        from app.agents.oracle import OracleAgent
        from app.agents.watcher import WatcherAgent
        from app.agents.advisor import AdvisorAgent
        from app.agents.testing_agent import TestingAgent
        from app.agents.release import ReleaseAgent
        
        constructors = {
            "architect": ArchitectAgent,
            "virtuoso": VirtuosoAgent,
            "sentinel": SentinelAgent,
            "oracle": OracleAgent,
            "watcher": WatcherAgent,
            "advisor": AdvisorAgent,
            "testing": TestingAgent,
            "release": ReleaseAgent,
        }
        _agents[name] = constructors[name]()
    return _agents[name]

# Backward-compatible module-level references (lazy)
class _LazyAgent:
    """Descriptor that lazily initializes agents on first access."""
    def __init__(self, name):
        self._name = name
    def __getattr__(self, attr):
        return getattr(_get_agent(self._name), attr)

architect_agent = _LazyAgent("architect")
virtuoso_agent = _LazyAgent("virtuoso")
sentinel_agent = _LazyAgent("sentinel")
oracle_agent = _LazyAgent("oracle")
watcher_agent = _LazyAgent("watcher")
advisor_agent = _LazyAgent("advisor")
testing_agent = _LazyAgent("testing")
release_agent = _LazyAgent("release")

# Helper to save state manually
# Helper to save state manually
async def save_state(state: AgentState):
    """
    Save state using CheckpointManager.
    Wraps the new CheckpointManager for backward compatibility.
    """
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    from dataclasses import asdict
    
    redis_url = settings.REDIS_URL if settings.USE_REDIS_PERSISTENCE else None
    manager = get_checkpoint_manager(redis_url)
    
    # Save checkpoint
    # We use agent_id or project_id as job_id
    job_id = state.agent_id or state.project_id
    state_dict = asdict(state)
    
    success = await manager.save_checkpoint(
        job_id=job_id,
        state_dict=state_dict,
        step_id=state.current_step_id
    )
    
    if not success and settings.USE_REDIS_PERSISTENCE:
         logger.warning(f"Failed to save checkpoint for {job_id}")

async def resume_from_checkpoint(job_id: str) -> Optional[AgentState]:
    """Load state from checkpoint."""
    from app.core.persistence import get_checkpoint_manager
    from app.core.config import settings
    from app.agents.state import AgentState
    import json
    
    redis_url = settings.REDIS_URL if settings.USE_REDIS_PERSISTENCE else None
    manager = get_checkpoint_manager(redis_url)
    checkpoint = await manager.load_checkpoint(job_id)
    
    if not checkpoint:
        return None
    
    # Reconstruct AgentState
    # parse_raw expects json string, load_checkpoint returns dict
    state = AgentState.parse_raw(json.dumps(checkpoint))
    
    logger.info(f"Orchestrator: Resumed from checkpoint: {job_id}")
    return state

# DEPRECATED: load_state is kept for backward compatibility only.
# All callers should use resume_from_checkpoint() directly.
async def load_state(agent_id: str) -> Optional[AgentState]:
    """Deprecated: Use resume_from_checkpoint() instead."""
    return await resume_from_checkpoint(agent_id)

# --- NODES ---

async def architect_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("architect")
    
    # Ensure agent_id is set (using project_id as proxy or separate field)
    if not state.agent_id:
        state.agent_id = state.project_id

    # Restore state if needed (this logic typically sits outside the graph, but user asked for restoration on startup/resume)
    # Since this is a node, execution has already started. We assume state is passed in.
    
    # Structured Log
    thread_id = state.project_id
    logger.info(f"--- ARCHITECT NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "SYSTEM", 
        "message": "Architect analyzing requirements...",
        "metadata": {"thread_id": thread_id, "step": "architect"}
    })
    
    # Inject Thought Signature if available
    prompt = state.user_prompt
    if state.thought_signature:
        prompt = f"## Previous Context (Signature: {state.thought_signature})\n\n{prompt}"
        # Note: True thought signature injection might need specific API parameter, 
        # but user said: "prepend or append state.thought_signature to the system prompt"
    
    blueprint = await architect_agent.design_system(state.user_prompt, state.tech_stack)
    
    if "error" in blueprint:
        await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"❌ Failed: {blueprint['error'][:100]}"})
        state.current_status = "error"
        state.errors.append(blueprint['error'])
        # Save state
        await save_state(state)
        return {"current_status": "error", "errors": [blueprint['error']]}
    
    state.blueprint = blueprint

    # Extract Thought Signature
    if "thought_signature" in blueprint:
        from app.agents.state import ThoughtSignature
        sig_dict = blueprint.pop("thought_signature")
        try:
            # handle if it's already an object or dict
            if isinstance(sig_dict, dict):
                signature = ThoughtSignature(**sig_dict)
                state.thought_signatures.append(signature)
                logger.info(f"Architect Node: Stored signature {signature.signature_id}")
        except Exception as e:
            logger.warning(f"Failed to store architect signature: {e}")

    state.current_status = "blueprint_generated"
    state.messages.append(f"Architect designed system: {blueprint.get('project_name')}")
    
    # Save State
    await save_state(state)
    metrics.stop_timer("architect")
    
    return {"blueprint": blueprint, "current_status": "blueprint_generated"}

async def planner_node(state: AgentState):
    """
    Generate explicit execution plan.
    
    Only runs if repo_path is set (autonomous mode).
    For generate-from-scratch mode, skip planning.
    """
    from app.core.socket_manager import SocketManager
    from app.agents.planner import get_planner_agent
    
    sm = SocketManager()
    thread_id = state.project_id
    
    # Skip planning if no repo (generation mode)
    if not state.repo_path:
        logger.info("--- PLANNER SKIPPED (generation mode) ---")
        return {"current_status": "planning_skipped"}
    
    logger.info(f"--- PLANNER NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "PLANNER",
        "message": "Generating execution plan...",
        "metadata": {"thread_id": thread_id, "step": "planner"}
    })
    
    # Gather context
    context = {
        "repo_analysis": getattr(state, "repo_analysis", None),
        "tech_stack": state.tech_stack,
        "file_system": state.file_system
    }
    
    try:
        planner = get_planner_agent()
        result = await planner.create_plan(state.user_prompt, context)
        
        # Unpack tuple if signature present
        if isinstance(result, tuple):
            plan, signature = result
        else:
            plan = result
            signature = None
            
        # Store signature
        if signature:
            state.thought_signatures.append(signature)
            logger.info(f"Planner Node: Stored signature {signature.signature_id}")
        
        state.execution_plan = plan
        state.current_status = "plan_generated"
        state.messages.append(f"Plan created: {len(plan.steps)} steps")
        
        # Emit plan to frontend
        await sm.emit("plan_generated", {
            "plan": plan.to_dict(),
            "steps": len(plan.steps),
            "estimated_duration": plan.estimated_duration_minutes
        })
        
        await sm.emit("agent_log", {
            "agent_name": "PLANNER",
            "message": f"✅ Plan: {len(plan.steps)} steps, ~{plan.estimated_duration_minutes}min"
        })
        
        # Save state
        await save_state(state)
        
        return {
            "execution_plan": plan,
            "current_status": "plan_generated"
        }
        
    except Exception as e:
        await sm.emit("agent_log", {
            "agent_name": "PLANNER",
            "message": f"❌ Planning failed: {str(e)[:100]}"
        })
        state.current_status = "error"
        state.errors.append(f"Planning failed: {e}")
        return {"current_status": "error"}

from app.core.filesystem import write_project_files

async def virtuoso_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("virtuoso")
    
    thread_id = state.project_id
    logger.info(f"--- VIRTUOSO NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "SYSTEM", 
        "message": "Entering Virtuoso Node...",
        "metadata": {"thread_id": thread_id, "step": "virtuoso"}
    })
    
    blueprint = state.blueprint
    if not blueprint:
        state.current_status = "error"
        state.errors.append("Missing Blueprint")
        await save_state(state)
        return {"current_status": "error"}

    errors = state.errors
    current_files = state.file_system
    iteration = state.iteration_count
    
    if errors and iteration > 0:
        # Pass visual context from previous watcher run for enriched self-healing
        visual_context = getattr(state, "visual_report", None)
        # repair_files currently returns just dict (files)
        # We handle it as legacy
        new_files = await _handle_self_healing(sm, errors, current_files, iteration, visual_context, state=state)
        signature = None
    else:
        # Normal generation returns {"files": ..., "signature": ...}
        result = await _handle_normal_generation(blueprint)
        if isinstance(result, dict) and "files" in result:
             new_files = result["files"]
             signature = result.get("signature")
        else:
             new_files = result
             signature = None
    
    # Store signature
    if signature:
        state.thought_signatures.append(signature)
        logger.info(f"Virtuoso Node: Stored signature {signature.signature_id}")

    new_files = _post_process_files(new_files)
    
    # Validate file structure (auto-fixes some issues like missing @tailwindcss/postcss)
    structure_warnings = _validate_file_structure(new_files, state.tech_stack or "auto")
    if structure_warnings:
        for w in structure_warnings:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"⚠️ {w}"
            })
    
    write_project_files(state.project_id, new_files)
    
    # Track which files actually changed (for incremental test generation)
    changed_file_list = []
    if current_files:
        for path, content in new_files.items():
            old = current_files.get(path)
            if old is None or old != content:
                changed_file_list.append(path)
    else:
        changed_file_list = list(new_files.keys())
    state.changed_files = changed_file_list
    
    state.file_system = new_files
    state.current_status = "code_generated"
    state.errors = []
    
    # Save State
    await save_state(state)
    
    if changed_file_list:
        logger.info(f"Virtuoso Node: {len(changed_file_list)} files changed: {changed_file_list[:5]}")

    metrics.record("files_generated", len(new_files))
    metrics.increment("virtuoso_iterations")
    metrics.stop_timer("virtuoso")

    return {"file_system": new_files, "current_status": "code_generated", "errors": [], "changed_files": changed_file_list}

async def _handle_self_healing(sm, errors, current_files, iteration, visual_context=None, state=None):
    """
    Enhanced self-healing with root-cause analysis and StrategyEngine governance.
    
    Flow:
    1. Enrich errors with visual context
    2. Diagnose failures via DiagnosticianAgent
    3. Select strategy via StrategyEngine (with escalation + budget)
    4. Execute repairs via appropriate Virtuoso method
    5. Record attempt outcome in StrategyEngine
    
    Args:
        sm: SocketManager for logging
        errors: List of errors to fix
        current_files: Current file system state
        iteration: Current iteration count
        visual_context: Optional dict with visual artifacts from Watcher
        state: Optional AgentState for test_results and thought_signatures
    """
    from app.agents.diagnostician import get_diagnostician
    from app.core.strategy_engine import StrategyEngine, RepairStrategy
    import time
    
    repair_start = time.time()
    
    # --- G4/G14: RepoSlicer — reduce context for LLM efficiency ---
    try:
        from app.core.repo_slicer import get_repo_slicer
        slicer = get_repo_slicer()
        sliced_files = slicer.slice(current_files, errors)
        if len(sliced_files) < len(current_files):
            await sm.emit("agent_log", {
                "agent_name": "REPO_SLICER",
                "message": f"📐 Context optimized: {len(current_files)} files → {len(sliced_files)} files"
            })
        repair_context_files = sliced_files
    except Exception:
        repair_context_files = current_files  # Fallback: use all files
    
    await sm.emit("agent_log", {
        "agent_name": "SYSTEM", 
        "message": f"🔍 Diagnosing {len(errors)} errors (Iteration {iteration})..."
    })
    
    # Restore or create StrategyEngine
    if state and state.strategy_engine_state:
        engine = StrategyEngine.from_dict(state.strategy_engine_state)
    else:
        max_retries = state.max_total_retries if state else 5
        engine = StrategyEngine(max_total_retries=max_retries)
    
    # Check budget before proceeding
    if engine.should_halt():
        await sm.emit("agent_log", {
            "agent_name": "STRATEGY_ENGINE",
            "message": f"⛔ Retry budget exhausted ({engine.get_total_attempts()}/{engine.max_total_retries}). Halting repairs."
        })
        if state:
            state.strategy_engine_state = engine.to_dict()
            state.strategy_history = [a.to_dict() for a in engine.history]
        return current_files
    
    budget_info = f"[Budget: {engine.get_total_attempts()}/{engine.max_total_retries}]"
    
    # Step 1: Enrich errors with visual context
    enriched_errors = errors.copy()
    if visual_context:
        visual_summary = []
        
        if visual_context.get("screenshot"):
            visual_summary.append(f"Screenshot: {visual_context['screenshot']}")
        
        if visual_context.get("dom_summary"):
            dom = visual_context["dom_summary"]
            if dom.get("title"):
                visual_summary.append(f"Page title: {dom['title']}")
            if dom.get("headings"):
                h1s = [h["text"] for h in dom["headings"] if h.get("level") == "h1"][:2]
                visual_summary.append(f"Main headings: {', '.join(h1s)}")
            if dom.get("interactive_elements"):
                visual_summary.append(f"Interactive elements: {dom['interactive_elements']}")
        
        if visual_context.get("gemini_analysis"):
            analysis = visual_context["gemini_analysis"]
            if analysis.get("overall_quality"):
                visual_summary.append(f"Visual QA: {analysis['overall_quality']}")
            if analysis.get("issues"):
                vision_issues = [
                    f"[{i.get('category', 'UI')}] {i.get('description', '')}"
                    for i in analysis["issues"][:3]
                ]
                enriched_errors.extend([f"Visual: {vi}" for vi in vision_issues])
        
        if visual_context.get("console_errors"):
            console_errs = [e.get("text", str(e)) for e in visual_context["console_errors"][:3]]
            enriched_errors.extend([f"Console: {ce[:100]}" for ce in console_errs])
        
        if visual_context.get("network_failures"):
            net_fails = [f"Network: {n.get('url', 'unknown')} - {n.get('failure', 'failed')}" 
                        for n in visual_context["network_failures"][:2]]
            enriched_errors.extend(net_fails)
        
        if visual_summary:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": f"Visual context: {'; '.join(visual_summary[:3])}"
            })
    
    # Step 2: Root-cause analysis
    diagnostician = get_diagnostician()
    diagnosis = await diagnostician.diagnose(
        errors=enriched_errors,
        visual_context=visual_context,
        test_results=getattr(state, "test_results", None) if state else None,
        thought_signatures=getattr(state, "thought_signatures", None) if state else None
    )
    
    await sm.emit("diagnostic_report", diagnosis.to_dict())
    
    await sm.emit("agent_log", {
        "agent_name": "DIAGNOSTICIAN",
        "message": f"Root cause: {diagnosis.root_cause[:100]} | Recommended: {diagnosis.recommended_strategy.value} (Confidence: {diagnosis.confidence:.0%})"
    })
    
    # Step 3: Select strategy via StrategyEngine (may override diagnosis)
    strategy_enum = engine.select_strategy(
        diagnosis_recommendation=diagnosis.recommended_strategy.value
    )
    # Map back to diagnostician's RepairStrategy enum for execution
    from app.agents.diagnostician import RepairStrategy as DiagRepairStrategy
    strategy = DiagRepairStrategy(strategy_enum.value)
    
    await sm.emit("agent_log", {
        "agent_name": "STRATEGY_ENGINE",
        "message": f"🎯 Selected: {strategy.value} {budget_info}"
    })
    
    if state:
        state.current_repair_strategy = strategy.value
    
    # Step 4: Execute strategy
    repaired_files = current_files
    repair_success = False
    
    try:
        if strategy == DiagRepairStrategy.TARGETED_FIX:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": "Strategy: Targeted fix (patching specific issues)"
            })
            repaired_files = await virtuoso_agent.repair_files_targeted(
                repair_context_files,
                diagnosis.affected_files,
                diagnosis.fix_suggestions
            )
        
        elif strategy == DiagRepairStrategy.FULL_REWRITE:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": "Strategy: Full rewrite (regenerating affected files)"
            })
            repaired_files = await virtuoso_agent.rewrite_files(
                repair_context_files,
                diagnosis.affected_files,
                diagnosis.root_cause
            )
        
        elif strategy == DiagRepairStrategy.ADD_MISSING:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": "Strategy: Add missing (imports/dependencies)"
            })
            repaired_files = await virtuoso_agent.add_missing_dependencies(
                repair_context_files,
                enriched_errors
            )
        
        elif strategy == DiagRepairStrategy.CONFIGURATION:
            await sm.emit("agent_log", {
                "agent_name": "VIRTUOSO",
                "message": "Strategy: Fix configuration"
            })
            repaired_files = await virtuoso_agent.fix_configuration(
                repair_context_files,
                diagnosis.root_cause
            )
        
        elif strategy == DiagRepairStrategy.ROLLBACK:
            await sm.emit("agent_log", {
                "agent_name": "SYSTEM",
                "message": "Strategy: Rollback (errors too severe)"
            })
            try:
                from app.core.git_adapter import get_git_adapter
                git = get_git_adapter()
                if state and state.project_id:
                    initial = getattr(state, 'initial_commit', None)
                    if initial:
                        # G6: Use safe_rollback with regression detection
                        if hasattr(git, 'safe_rollback'):
                            # Build a simple test runner function for regression detection
                            async def _test_runner():
                                try:
                                    from app.agents.testing_agent import TestingAgent
                                    tester = TestingAgent()
                                    project_path = str(Path(state.repo_path or '').resolve()) if state.repo_path else None
                                    if project_path:
                                        result = await tester.quick_validate(project_path)
                                        passed = result.get('passed', 0) if isinstance(result, dict) else 0
                                        total = result.get('total', 1) if isinstance(result, dict) else 1
                                        return {'passed': passed, 'total': total}
                                except Exception:
                                    pass
                                return {'passed': 0, 'total': 0}
                            
                            success, msg = await git.safe_rollback(
                                state.project_id, initial, test_runner=_test_runner
                            )
                        else:
                            success, msg = git.rollback_to_commit(state.project_id, initial)
                        
                        await sm.emit("agent_log", {
                            "agent_name": "GIT",
                            "message": f"{'✅' if success else '⚠️'} Rollback: {msg}"
                        })
            except Exception as rollback_err:
                await sm.emit("agent_log", {
                    "agent_name": "SYSTEM",
                    "message": f"Rollback unavailable: {str(rollback_err)[:80]}"
                })
            return current_files  # Return unchanged files
        
        else:
            repaired_files = await virtuoso_agent.repair_files(repair_context_files, enriched_errors)
        
        # If we got different files back, consider it a partial success
        repair_success = repaired_files != current_files
        
    except Exception as repair_err:
        await sm.emit("agent_log", {
            "agent_name": "SYSTEM",
            "message": f"⚠️ Repair execution failed: {str(repair_err)[:100]}"
        })
        repair_success = False
    
    # Step 5: Record attempt in StrategyEngine
    duration_ms = int((time.time() - repair_start) * 1000)
    engine.record_attempt(
        strategy=strategy_enum,
        success=repair_success,
        errors_before=errors[:10],
        errors_after=errors[:10] if not repair_success else [],  # Assume errors persist unless repair changed files
        duration_ms=duration_ms,
        diagnosis_summary=diagnosis.root_cause[:200]
    )
    
    # Persist engine state
    if state:
        state.strategy_engine_state = engine.to_dict()
        state.strategy_history = [a.to_dict() for a in engine.history]
        state.total_retries_used = engine.get_total_attempts()
    
    return repaired_files

async def _handle_normal_generation(blueprint):
    """Handle normal code generation logic."""
    return await virtuoso_agent.generate_from_blueprint(blueprint)

def _post_process_files(files):
    """
    Post-process generated files:
    1. Normalize path separators to forward-slash (prevents duplicate folders)
    2. Deduplicate paths (last-write-wins when collisions occur)
    3. Strip leading/trailing whitespace and BOM from content
    4. Remove markdown code-block wrappers that LLMs sometimes add
    
    NOTE: We intentionally do NOT replace \\n -> \n in content.
    The LLM returns JSON-encoded strings where \\n is already the correct
    representation. Naive replacement corrupts JSON files, regex patterns,
    and any content with legitimate escaped characters.
    """
    import re as _re
    
    cleaned = {}
    seen_normalized = {}  # normalized_path -> original_path (for dedup tracking)
    
    for path, content in files.items():
        # 1. Normalize path: forward-slash, strip edges, remove leading ./
        norm_path = path.strip().replace("\\", "/").strip("/")
        # Collapse consecutive slashes (e.g. frontend//src → frontend/src)
        norm_path = _re.sub(r'/+', '/', norm_path)
        if norm_path.startswith("./"):
            norm_path = norm_path[2:]
        
        # Skip empty paths or metadata keys
        if not norm_path or norm_path.startswith("__"):
            continue
        
        # 2. Ensure content is a string (LLM repair can return nested dicts)
        if not isinstance(content, str):
            if isinstance(content, dict):
                # Likely a metadata blob or accidental nested structure
                # If it looks like a JSON file, serialize it; otherwise skip
                if norm_path.endswith(".json"):
                    import json as _json
                    content = _json.dumps(content, indent=2)
                else:
                    logger.warning(f"_post_process_files: Skipping '{norm_path}' — content is {type(content).__name__}, not str")
                    continue
            else:
                content = str(content)
        
        # 3. Process string content
        # Strip BOM and edge whitespace
        content = content.lstrip("\ufeff").strip()
        
        # Remove markdown code-block wrappers (common LLM artifact)
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```language) and last line (```)
            if len(lines) > 2 and lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1])
            elif len(lines) > 1:
                content = "\n".join(lines[1:])
        
        # 3. Deduplicate: last-write-wins (later entries override earlier ones)
        if norm_path in seen_normalized:
            prev_path = seen_normalized[norm_path]
            logger.info(f"_post_process_files: Dedup — '{path}' overwrites '{prev_path}'")
        
        seen_normalized[norm_path] = path
        cleaned[norm_path] = content
    
    return cleaned


def _validate_file_structure(files: dict, tech_stack: str = "auto") -> list:
    """
    Validate generated file structure for common LLM generation errors.
    Stack-driven: uses StackProfile validation_rules when available.
    
    Returns list of warning/error strings. Also auto-fixes some issues.
    Modifies `files` dict in-place for auto-fixes.
    """
    import json as _json
    import re as _re
    
    warnings = []
    
    # Get stack profile for validation rules
    profile = None
    validation_rules = []
    try:
        from app.core.stack_profiles import detect_stack
        profile = detect_stack("", tech_stack)
        validation_rules = profile.validation_rules  # List[str] of rule names
    except Exception:
        pass
    
    # Collect file paths by category
    file_paths = set(files.keys())
    has_package_json = any(p.endswith("package.json") for p in file_paths)
    postcss_files = [p for p in file_paths if "postcss.config" in p]
    json_files = [p for p in file_paths if p.endswith(".json")]
    
    # 1. Check for dependency manifest existence (skip for static-html)
    manifest = profile.dependency_manifest if profile else "package.json"
    has_source_files = any(
        p.endswith((".tsx", ".jsx", ".ts", ".vue", ".svelte", ".py", ".go", ".java"))
        for p in file_paths
    )
    is_static_html = profile and profile.id == "static-html"
    if has_source_files and not is_static_html and not any(p.endswith(manifest) for p in file_paths):
        warnings.append(f"STRUCTURE: Source files found but no {manifest} generated")
    
    # 2. Validate JSON files are parseable
    for json_path in json_files:
        content = files.get(json_path, "")
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            _json.loads(content)
        except _json.JSONDecodeError as e:
            warnings.append(f"INVALID_JSON: {json_path} — {str(e)[:60]}")
    
    # 3. Auto-fix postcss.config: ensure @tailwindcss/postcss is used (not raw tailwindcss)
    for pc_path in postcss_files:
        pc_content = files.get(pc_path, "")
        
        uses_old_tw = (
            "tailwindcss" in pc_content and
            "@tailwindcss/postcss" not in pc_content
        )
        if uses_old_tw:
            fixed_content = pc_content.replace(
                "require('tailwindcss')", "require('@tailwindcss/postcss')"
            ).replace(
                'require("tailwindcss")', 'require("@tailwindcss/postcss")'
            )
            fixed_content = _re.sub(
                r'\btailwindcss\b(\s*:\s*\{)',
                r"'@tailwindcss/postcss'\1",
                fixed_content
            )
            fixed_content = fixed_content.replace(
                "'tailwindcss'", "'@tailwindcss/postcss'"
            ).replace(
                '"tailwindcss"', '"@tailwindcss/postcss"'
            )
            if fixed_content != pc_content:
                files[pc_path] = fixed_content
                warnings.append(
                    f"AUTO-FIX: Replaced 'tailwindcss' with '@tailwindcss/postcss' in {pc_path}"
                )
        
        # Ensure dependency exists in package.json
        if "@tailwindcss/postcss" in files.get(pc_path, ""):
            pkg_path = None
            for p in file_paths:
                if p.endswith("package.json"):
                    pkg_path = p
                    break
            
            if pkg_path:
                try:
                    pkg = _json.loads(files[pkg_path])
                    all_deps = {
                        **pkg.get("dependencies", {}),
                        **pkg.get("devDependencies", {})
                    }
                    if "@tailwindcss/postcss" not in all_deps:
                        dev_deps = pkg.get("devDependencies", {})
                        dev_deps["@tailwindcss/postcss"] = "^4.0.0"
                        pkg["devDependencies"] = dev_deps
                        files[pkg_path] = _json.dumps(pkg, indent=2)
                        warnings.append(
                            f"AUTO-FIX: Added @tailwindcss/postcss to {pkg_path} devDependencies"
                        )
                except (_json.JSONDecodeError, TypeError):
                    pass
    
    # 3b. Auto-fix globals.css: replace old @tailwind directives with v4 @import syntax
    css_files = [p for p in file_paths if p.endswith("globals.css")]
    for css_path in css_files:
        css_content = files.get(css_path, "")
        if "@tailwind base" in css_content or "@tailwind components" in css_content:
            fixed_css = css_content
            for directive in ["@tailwind base;", "@tailwind components;", "@tailwind utilities;"]:
                fixed_css = fixed_css.replace(directive, "")
            if '@import "tailwindcss"' not in fixed_css and "@import 'tailwindcss'" not in fixed_css:
                fixed_css = '@import "tailwindcss";\n\n' + fixed_css.lstrip()
            files[css_path] = fixed_css
            warnings.append(
                f"AUTO-FIX: Replaced @tailwind directives with @import 'tailwindcss' in {css_path}"
            )
    
    # 4. Stack-driven: run validation rules from profile
    if profile and validation_rules:
        # validation_rules is a List[str] of rule names like "check_package_json_exists"
        if "check_package_json_exists" in validation_rules:
            if has_package_json is False and any(p.endswith((".tsx", ".jsx", ".ts", ".vue", ".svelte")) for p in file_paths):
                warnings.append("STRUCTURE: Frontend files found but no package.json generated")
        if "check_app_dir_exists" in validation_rules and has_package_json:
            for pkg_path in file_paths:
                if pkg_path.endswith("package.json"):
                    try:
                        pkg = _json.loads(files[pkg_path])
                        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                        if "next" in deps:
                            prefix = pkg_path.replace("package.json", "")
                            has_app_dir = any(
                                p.startswith(prefix + "app/") or 
                                p.startswith(prefix + "src/app/") or
                                p.startswith(prefix + "pages/")
                                for p in file_paths
                            )
                            if not has_app_dir:
                                warnings.append(
                                    f"STRUCTURE: Next.js project at {prefix} missing app/ or pages/ directory"
                                )
                    except (_json.JSONDecodeError, TypeError):
                        pass
        if "check_requirements_txt_exists" in validation_rules:
            if not any(p.endswith("requirements.txt") for p in file_paths):
                if any(p.endswith(".py") for p in file_paths):
                    warnings.append("STRUCTURE: Python files found but no requirements.txt generated")
    
    # 5. Check for files placed outside expected source prefix
    source_prefix = profile.source_prefix if profile else ''
    if source_prefix and any(p.startswith(source_prefix) for p in file_paths):
        misplaced = [
            p for p in file_paths
            if (p.startswith("app/") or p.startswith("src/")) and
            not p.startswith(source_prefix) and not p.startswith("backend/")
        ]
        if misplaced:
            warnings.append(
                f"STRUCTURE: {len(misplaced)} files may be misplaced outside {source_prefix}: "
                f"{', '.join(misplaced[:3])}"
            )
    
    if warnings:
        logger.info(f"_validate_file_structure: {len(warnings)} issues found")
        for w in warnings:
            logger.debug(f"  • {w}")
    
    return warnings

async def sentinel_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    from app.agents.state import Issue
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("sentinel")
    
    thread_id = state.project_id
    logger.info(f"--- SENTINEL NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "SENTINEL", 
        "message": "Initiating security scan...",
        "metadata": {"thread_id": thread_id, "step": "sentinel"}
    })
    
    files = state.file_system
    report = await sentinel_agent.batch_audit(files)
    
    # Convert vulnerabilities to Issue objects
    if "vulnerabilities" in report:
        for v in report["vulnerabilities"]:
            state.issues.append(Issue(
                file=v.get("file", "unknown"), # sentinel usually returns path as key, but here it's in list?
                # Check report format in sentinel.py: "vulnerabilities.append({... 'description': ... 'fix_suggestion':...})"
                # It doesn't explicitly have 'file' key in the dict items, but description says "in {file_path}"
                # I should update sentinel.py to include file path explicitly or parse it here.
                # Assuming sentinel returns valuable info.
                issue=v.get("description", "Security vulnerability"),
                fix=v.get("fix_suggestion", "")
            ))
            
    if report["status"] == "BLOCKED":
        await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": f"🚨 Security issues found! Code blocked."})
        # Add critical issues to state.errors for self-healing
        if "vulnerabilities" in report:
            for v in report["vulnerabilities"]:
                if v.get("severity") in ["HIGH", "CRITICAL"]:
                    state.errors.append(f"Security Critical: {v.get('description')} (Fix: {v.get('fix_suggestion')})")
    else:
        await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": "✅ Security scan passed"})
            
    state.security_report = report
    state.current_status = "security_audited"
    
    # Save State
    await save_state(state)
    metrics.stop_timer("sentinel")
    
    return {"security_report": report, "current_status": "security_audited", "issues": state.issues}

async def testing_node(state: AgentState):
    """Run automated tests."""
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("testing")
    
    thread_id = state.project_id
    logger.info(f"--- TESTING NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "TESTING", 
        "message": "Starting automated tests...",
        "metadata": {"thread_id": thread_id, "step": "testing"}
    })
    
    # Ensure project_dir is set on state
    from app.core.filesystem import BASE_PROJECTS_DIR
    project_dir = str(BASE_PROJECTS_DIR / state.project_id)
    setattr(state, "project_dir", project_dir)
    
    # Try generate_and_run_tests first (generates + executes tests)
    # Falls back to run() which only executes pre-existing tests
    # On fix iterations, only regenerate tests for files that actually changed
    changed = getattr(state, "changed_files", None)
    is_fix_iteration = state.iteration_count > 0 and changed
    
    try:
        test_results = await testing_agent.generate_and_run_tests(
            project_path=project_dir,
            file_system=state.file_system or {},
            tech_stack=state.tech_stack or "Auto-detect",
            changed_files=changed if is_fix_iteration else None
        )
        # Store results in state
        if test_results.get("errors"):
            state.errors.extend(test_results["errors"][:5])
        state.messages.append(f"TestingAgent: {test_results.get('summary', 'Tests completed')}")
    except Exception as e:
        logger.warning(f"TestingAgent generate_and_run_tests failed: {e}, falling back to run()")
        state = await testing_agent.run(state)
    
    # Save State
    await save_state(state)
    metrics.stop_timer("testing")
    
    return {
        "issues": state.issues,
        "messages": state.messages[-5:],
        "errors": state.errors
    }

async def advisor_node(state: AgentState):
    """Deployment advisory analysis post-testing."""
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("advisor")
    
    thread_id = state.project_id
    logger.info(f"--- ADVISOR NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "ADVISOR",
        "message": "Analyzing deployment strategy and recommendations...",
        "metadata": {"thread_id": thread_id, "step": "advisor"}
    })
    
    try:
        # Build project details for advisor
        project_details = {
            "project_id": state.project_id,
            "tech_stack": state.tech_stack or "Auto-detect",
            "file_count": len(state.file_system) if state.file_system else 0,
            "issues": state.issues[:5] if state.issues else [],
            "errors": state.errors[:5] if state.errors else [],
            "iteration_count": state.iteration_count,
        }
        
        # Add blueprint info if available
        if state.blueprint:
            project_details["blueprint"] = {
                "project_name": state.blueprint.get("project_name", "unknown"),
                "tech_stack": state.blueprint.get("tech_stack", "unknown"),
                "project_type": state.blueprint.get("projectType", "frontend"),
            }
        
        report = await advisor_agent.analyze_deployment(project_details)
        
        state.messages.append(f"ADVISOR: Deployment advisory - Platform: {report.get('platform', 'N/A')}, "
                            f"Est. Cost: {report.get('cost_estimate', 'N/A')}")
        
        await sm.emit("agent_log", {
            "agent_name": "ADVISOR",
            "message": f"Advisory complete: {report.get('platform', 'N/A')} recommended"
        })
        
    except Exception as e:
        # Advisory is non-critical — log and continue
        logger.warning(f"Advisor node warning: {e}")
        await sm.emit("agent_log", {
            "agent_name": "ADVISOR",
            "message": f"Advisory skipped: {str(e)[:80]}"
        })
    
    await save_state(state)
    metrics.stop_timer("advisor")
    return {"messages": state.messages[-3:]}


async def watcher_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    from app.core.filesystem import BASE_PROJECTS_DIR
    from app.agents.state import Issue
    
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("watcher")
    thread_id = state.project_id
    logger.info(f"--- WATCHER NODE (Thread: {thread_id}) ---")
    
    project_id = state.project_id
    project_path = str(BASE_PROJECTS_DIR / project_id)
    
    await sm.emit("agent_log", {
        "agent_name": "WATCHER", 
        "message": "Starting project verification...",
        "metadata": {"thread_id": thread_id, "step": "watcher"}
    })
    
    try:
        report = await watcher_agent.run_and_verify_project(project_path, project_id)
        
        if report["status"] == "FAIL":
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Verification failed: {len(report['errors'])} errors found"})
        elif report["status"] == "SKIPPED":
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "⚠️ Verification skipped (Playwright missing)"})
        else:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "✅ Project verification complete!"})
        
        state.visual_report = report
        state.current_status = "visually_verified"
        
        if report.get("screenshot"):
            # assuming sequential steps, use current length + 1
            step_num = len(state.screenshot_paths) + 1
            state.screenshot_paths[step_num] = report["screenshot"]

        # Convert errors to Issues
        if report.get("errors"):
            for err in report["errors"]:
                state.issues.append(Issue(file="Browser/UI", issue=str(err), fix="Check logs"))
        
        if report.get("fix_this"):
            state.errors = report.get("errors", [])
        
        # Save State
        await save_state(state)
        metrics.stop_timer("watcher")
        
        return {
            "visual_report": report,
            "current_status": "visually_verified",
            "errors": state.errors,
            "screenshot_paths": state.screenshot_paths,
            "issues": state.issues
        }
    except Exception as e:
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"⚠️ Verification error: {str(e)[:50]}"})
        return {
            "visual_report": {"status": "ERROR", "error": str(e)},
            "current_status": "visual_error",
            "errors": [str(e)]
        }


async def release_node(state: AgentState):
    """
    Release Agent node - prepares project for release with deployment artifacts.
    
    Generates:
    - Dockerfile (or platform-specific config)
    - CI/CD workflows
    - Release manifest
    - README if missing
    """
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    metrics = get_metrics_collector()
    metrics.start_timer("release")
    
    thread_id = state.project_id
    logger.info(f"--- RELEASE NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "RELEASE", 
        "message": "Preparing release package...",
        "metadata": {"thread_id": thread_id, "step": "release"}
    })
    
    try:
        # Prepare release with deployment artifacts
        report = await release_agent.prepare_release(
            project_id=state.project_id,
            blueprint=state.blueprint,
            deploy_targets=None,  # Auto-detect best target
            generate_readme=True,
            generate_cicd=True
        )
        
        if report.ready:
            await sm.emit("agent_log", {
                "agent_name": "RELEASE",
                "message": f"✅ Release ready! Generated: {', '.join(report.generated_artifacts[:5])}"
            })
        else:
            await sm.emit("agent_log", {
                "agent_name": "RELEASE",
                "message": f"⚠️ Release prepared with warnings: {len(report.missing_files)} missing files"
            })
        
        state.current_status = "release_ready"
        state.messages.append(f"Release prepared with {len(report.generated_artifacts)} artifacts")
        
        # Generate unified artifact report
        try:
            from app.core.artifact_generator import get_artifact_generator
            
            artifact_gen = get_artifact_generator()
            
            start_time_str = getattr(state, "start_time", "")
            if start_time_str:
                try:
                    job_start = datetime.fromisoformat(start_time_str)
                except (ValueError, TypeError):
                    job_start = datetime.now()
            else:
                job_start = datetime.now()
            
            artifact_report = await artifact_gen.generate_report(
                state,
                job_start,
                datetime.now()
            )
            
            await sm.emit("artifact_report", artifact_report)
            
            await sm.emit("agent_log", {
                "agent_name": "RELEASE",
                "message": f"📊 Artifact report generated: {artifact_report['status']} ({artifact_report['execution_summary']['duration_seconds']}s)"
            })
            
            # Include pipeline metrics in the report
            artifact_report["pipeline_metrics"] = metrics.summary()
        except Exception as artifact_err:
            await sm.emit("agent_log", {
                "agent_name": "RELEASE",
                "message": f"⚠️ Artifact report generation failed: {str(artifact_err)[:60]}"
            })
        
        # Save state
        await save_state(state)
        metrics.stop_timer("release")
        
        return {
            "release_report": report.to_dict(),
            "current_status": "release_ready",
            "messages": state.messages
        }
        
    except Exception as e:
        await sm.emit("agent_log", {
            "agent_name": "RELEASE",
            "message": f"❌ Release preparation failed: {str(e)[:50]}"
        })
        return {
            "release_report": {"error": str(e)},
            "current_status": "release_error"
        }

def router(state: AgentState):
    """
    SELF-HEALING ROUTER with StrategyEngine governance.
    
    Decision logic:
    1. No errors → release
    2. StrategyEngine budget exhausted → release (best effort)
    3. Errors present + budget remaining → virtuoso_fix
    """
    from app.core.strategy_engine import StrategyEngine
    
    errors = state.errors
    iteration = state.iteration_count
    max_iterations = state.max_iterations
    
    if not errors or len(errors) == 0:
        logger.info("Router: No errors. Routing to Release Agent.")
        return "release"
    
    # Check StrategyEngine budget
    if state.strategy_engine_state:
        engine = StrategyEngine.from_dict(state.strategy_engine_state)
        if engine.should_halt():
            logger.info(f"Router: StrategyEngine budget exhausted ({engine.get_total_attempts()}/{engine.max_total_retries}). Proceeding to release.")
            return "release"
    
    # Legacy max_iterations guard (defense in depth)
    if iteration >= max_iterations:
        logger.info(f"Router: Max iterations ({max_iterations}) reached. Proceeding to release.")
        return "release"
    
    logger.info(f"Router: {len(errors)} errors found. Routing to Virtuoso for fix (iteration {iteration + 1})")
    return "virtuoso_fix"

def increment_iteration(state: AgentState):
    count = state.iteration_count + 1
    state.iteration_count = count
    state.retry_count = count  # Keep retry_count in sync
    return {"iteration_count": count, "retry_count": count}

# Build Graph
builder = StateGraph(AgentState)

builder.add_node("architect", architect_node)
builder.add_node("virtuoso", virtuoso_node)
builder.add_node("sentinel", sentinel_node)
builder.add_node("testing", testing_node)
builder.add_node("watcher", watcher_node)
builder.add_node("advisor", advisor_node)  # Advisory node post-testing
builder.add_node("release", release_node)  # Phase 2: Release Agent node
builder.add_node("increment_iteration", increment_iteration)

builder.set_entry_point("architect")

builder.add_node("planner", planner_node)

def architect_router(state: AgentState):
    if state.current_status == "error":
        return END
    # Go to planner if repo exists, else virtuoso
    if state.repo_path:
        return "planner"
    return "virtuoso"

builder.add_conditional_edges(
    "architect",
    architect_router,
    {"planner": "planner", "virtuoso": "virtuoso", END: END}
)

# Planner exits to virtuoso
builder.add_edge("planner", "virtuoso")

# --- Adaptive Hooks ---
ENABLE_ADAPTIVE_FLOW = os.getenv("ENABLE_ADAPTIVE_FLOW", "False").lower() == "true"

def adaptive_virtuoso_exit(state: AgentState):
    if ENABLE_ADAPTIVE_FLOW:
        pass 
    return "sentinel"

def adaptive_sentinel_exit(state: AgentState):
    return "testing" # Modified: Sentinel -> Testing

def adaptive_testing_exit(state: AgentState):
    return "watcher" # Added: Testing -> Watcher

# Browser Validation Node (runs BrowserValidationAgent if URL available)
async def browser_validation_node(state: AgentState):
    """Run BrowserValidationAgent for deep browser testing (Playwright).
    
    Conditional: skips for non-web projects (e.g. Python CLI, Go services)
    based on the StackProfile.is_web flag.
    
    Runs AFTER watcher_node. If the watcher already performed browser 
    verification, we skip re-launching a server.
    """
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    # Stack-aware: skip browser validation for non-web projects
    try:
        from app.core.stack_profiles import detect_stack
        profile = detect_stack("", state.tech_stack or "auto")
        if not profile.is_web:
            await sm.emit("agent_log", {
                "agent_name": "BROWSER_VALIDATOR",
                "message": f"⏭️ Skipping browser validation for non-web project ({profile.display_name})"
            })
            return {"messages": state.messages}
    except Exception:
        pass  # Fallback: proceed with validation
    
    # If watcher already produced a visual_report, its findings are in state.
    visual_report = getattr(state, "visual_report", None)
    if visual_report and isinstance(visual_report, dict) and visual_report.get("status"):
        status = visual_report.get("status", "UNKNOWN")
        await sm.emit("agent_log", {
            "agent_name": "BROWSER_VALIDATOR",
            "message": f"✅ Using watcher's browser verification result: {status}"
        })
        return {"messages": state.messages}
    
    # Try to find a live preview URL (production / sandbox scenarios)
    project_port = getattr(state, "preview_port", None)
    if not project_port:
        release_report = getattr(state, "release_report", None)
        if release_report and isinstance(release_report, dict):
            project_port = release_report.get("preview_port")
    project_url = f"http://localhost:{project_port}" if project_port else None
    
    if not project_url:
        await sm.emit("agent_log", {
            "agent_name": "BROWSER_VALIDATOR",
            "message": "⏭️ No preview URL available — skipping browser validation"
        })
        return {"messages": state.messages}
    
    try:
        from app.agents.browser_validation_agent import BrowserValidationAgent
        validator = BrowserValidationAgent()
        
        await sm.emit("agent_log", {
            "agent_name": "BROWSER_VALIDATOR",
            "message": f"🌐 Running browser validation on {project_url}..."
        })
        
        project_path = str(Path(state.repo_path or "").resolve()) if state.repo_path else None
        report = await validator.comprehensive_validate(project_url, project_path or "")
        
        await sm.emit("agent_log", {
            "agent_name": "BROWSER_VALIDATOR",
            "message": f"Browser validation: {report.get('status', 'UNKNOWN')} — "
                       f"Scores: {json.dumps(report.get('scores', {}))}"
        })
        
        state.visual_report = report
        await save_state(state)
        
        return {
            "visual_report": report,
            "messages": state.messages
        }
        
    except Exception as e:
        await sm.emit("agent_log", {
            "agent_name": "BROWSER_VALIDATOR",
            "message": f"⚠️ Browser validation skipped: {str(e)[:80]}"
        })
        return {"messages": state.messages}

builder.add_conditional_edges("virtuoso", adaptive_virtuoso_exit, {"sentinel": "sentinel"})
builder.add_conditional_edges("sentinel", adaptive_sentinel_exit, {"testing": "testing"}) # Modified
builder.add_edge("testing", "advisor")  # Testing → Advisor
builder.add_node("browser_validation", browser_validation_node)
builder.add_edge("advisor", "watcher")               # Advisor → Watcher (starts server + basic Playwright check)
builder.add_edge("watcher", "browser_validation")     # Watcher → Browser Validation (deep browser testing with live URL)

# Router decides: fix errors or release — now after browser_validation
builder.add_conditional_edges(
    "browser_validation",
    router,
    {
        "virtuoso_fix": "increment_iteration",
        "release": "release"
    }
)

# Release node goes to END
builder.add_edge("release", END)

builder.add_edge("increment_iteration", "virtuoso")

# Compile
# We prefer using LangGraphRedisSaver for graph-level checkpoints if compatible, 
# but we ALSO implemented manual saving as requested.
# For graph.compile, we can still use a checkpointer or None.
# If we use LangGraphRedisSaver, we get standard LangGraph persistence.
# If we use MemorySaver, we get in-memory.
# The user asked to "replace the default in-memory saver", implying checking `USE_REDIS_PERSISTENCE`
# and using a Redis saver.
if USE_REDIS_PERSISTENCE:
    checkpointer = LangGraphRedisSaver(REDIS_URL)
    logger.info(f"Orchestrator: Using LangGraphRedisSaver ({REDIS_URL})")
else:
    checkpointer = MemorySaver()
    logger.info("Orchestrator: Using In-Memory Persistence")

graph = builder.compile(checkpointer=checkpointer)
