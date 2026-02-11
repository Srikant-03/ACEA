# ACEA Sentinel - Orchestrator with Self-Healing Loop
# Manages the agent workflow with automatic error detection and fixing

import json
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents.state import AgentState
from app.agents.architect import ArchitectAgent
from app.agents.virtuoso import VirtuosoAgent
from app.agents.sentinel import SentinelAgent
from app.agents.oracle import OracleAgent
from app.agents.watcher import WatcherAgent
from app.agents.advisor import AdvisorAgent
from app.core.persistence import InMemorySaver, AsyncRedisSaver

# Initialize Agents
architect_agent = ArchitectAgent()
virtuoso_agent = VirtuosoAgent()
sentinel_agent = SentinelAgent()
oracle_agent = OracleAgent()
watcher_agent = WatcherAgent()
advisor_agent = AdvisorAgent()

async def architect_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    # Structured Log
    thread_id = state.get("project_id", "unknown")
    run_id = state.get("run_id", "unknown") 
    print(f"--- ARCHITECT NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "SYSTEM", 
        "message": "Architect analyzing requirements...",
        "metadata": {"thread_id": thread_id, "step": "architect"}
    })
    
    prompt = state["user_prompt"]
    tech_stack = state.get("tech_stack", "Auto-detect")
    blueprint = await architect_agent.design_system(prompt, tech_stack)
    
    if "error" in blueprint:
        await sm.emit("agent_log", {"agent_name": "ARCHITECT", "message": f"❌ Failed: {blueprint['error'][:100]}"})
        return {
            "blueprint": {},
            "current_status": "error", 
            "messages": [f"Architect Failed: {blueprint['error']}"],
            "errors": [blueprint['error']]
        }
    
    name = blueprint.get('project_name', 'Untitled')
    return {
        "blueprint": blueprint,
        "current_status": "blueprint_generated",
        "messages": [f"Architect designed system: {name}"]
    }

from app.core.filesystem import write_project_files

async def virtuoso_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    thread_id = state.get("project_id", "unknown")
    print(f"--- VIRTUOSO NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "SYSTEM", 
        "message": "Entering Virtuoso Node...",
        "metadata": {"thread_id": thread_id, "step": "virtuoso"}
    })
    
    # 1. Validate Blueprint
    blueprint = state.get("blueprint")
    if not blueprint:
        await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "ERROR: Blueprint is missing!"})
        return {"current_status": "error", "errors": ["Missing Blueprint"]}

    # 2. Determine Mode (Self-Healing vs Normal)
    errors = state.get("errors", [])
    current_files = state.get("file_system", {})
    iteration = state.get("iteration_count", 0)
    
    if errors and iteration > 0:
        new_files = await _handle_self_healing(sm, errors, current_files, iteration)
    else:
        new_files = await _handle_normal_generation(blueprint)
    
    # 3. Post-Process & Persist
    new_files = _post_process_files(new_files)
    write_project_files(state["project_id"], new_files)
    
    return {
        "file_system": new_files,
        "current_status": "code_generated",
        "messages": [f"Virtuoso generated {len(new_files)} files"],
        "errors": []  # Clear errors after regeneration
    }

async def _handle_self_healing(sm, errors, current_files, iteration):
    """Handle self-healing mode logic."""
    await sm.emit("agent_log", {
        "agent_name": "VIRTUOSO", 
        "message": f"🔧 Self-Healing Mode: Patching {len(errors)} errors (Iteration {iteration})..."
    })
    return await virtuoso_agent.repair_files(current_files, errors)

async def _handle_normal_generation(blueprint):
    """Handle normal code generation logic."""
    return await virtuoso_agent.generate_from_blueprint(blueprint)

def _post_process_files(files):
    """Unescape newlines and clean up file content."""
    cleaned = {}
    for path, content in files.items():
        if isinstance(content, str):
            cleaned[path] = content.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        else:
            cleaned[path] = content
    return cleaned


async def sentinel_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    thread_id = state.get("project_id", "unknown")
    print(f"--- SENTINEL NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "SENTINEL", 
        "message": "Initiating security scan...",
        "metadata": {"thread_id": thread_id, "step": "sentinel"}
    })
    
    files = state["file_system"]
    
    # OPTIMIZED: Use batch audit (0 API calls, pattern-based only)
    report = await sentinel_agent.batch_audit(files)
    
    if report["status"] == "BLOCKED":
        await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": f"🚨 Security issues found! Code blocked."})
    else:
        await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": "✅ Security scan passed"})
            
    return {
        "security_report": report,
        "current_status": "security_audited"
    }

async def watcher_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    from app.core.filesystem import BASE_PROJECTS_DIR
    
    sm = SocketManager()
    thread_id = state.get("project_id", "unknown")
    print(f"--- WATCHER NODE (Thread: {thread_id}) ---")
    
    project_id = state["project_id"]
    project_path = str(BASE_PROJECTS_DIR / project_id)
    
    await sm.emit("agent_log", {
        "agent_name": "WATCHER", 
        "message": "Starting project verification...",
        "metadata": {"thread_id": thread_id, "step": "watcher"}
    })
    
    try:
        # User requested FULL AUTONOMY: run code, check errors, fix errors.
        # We switch from quick_verify to run_and_verify_project
        report = await watcher_agent.run_and_verify_project(project_path, project_id)
        
        if report["status"] == "FAIL":
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Verification failed: {len(report['errors'])} errors found"})
        elif report["status"] == "SKIPPED":
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "⚠️ Verification skipped (Playwright missing)"})
        else:
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "✅ Project verification complete!"})
        
        return {
            "visual_report": report,
            "current_status": "visually_verified",
            "messages": [f"Watcher Status: {report['status']}"],
            "errors": report.get("errors", []) if report.get("fix_this") else []
        }
    except Exception as e:
        await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"⚠️ Verification error: {str(e)[:50]}"})
        return {
            "visual_report": {"status": "ERROR", "error": str(e)},
            "current_status": "visual_error",
            "messages": [f"Watcher Failed: {str(e)}"],
            "errors": [str(e)]
        }

def router(state: AgentState):
    """
    SELF-HEALING ROUTER
    Checks if there are errors that need fixing and routes back to Virtuoso.
    """
    errors = state.get("errors", [])
    iteration = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)
    
    # Check if we have errors to fix
    if errors and len(errors) > 0:
        if iteration >= max_iterations:
            print(f"Router: Max iterations ({max_iterations}) reached. Ending.")
            return END
        
        print(f"Router: Errors found. Routing to Virtuoso for fix (iteration {iteration + 1})")
        return "virtuoso_fix"
    
    # No errors - we're done!
    print("Router: No errors. Mission complete!")
    return END

def increment_iteration(state: AgentState):
    """Helper node to increment iteration count before fix."""
    return {"iteration_count": state.get("iteration_count", 0) + 1}

# Build Graph
builder = StateGraph(AgentState)

builder.add_node("architect", architect_node)
builder.add_node("virtuoso", virtuoso_node)
builder.add_node("sentinel", sentinel_node)
builder.add_node("watcher", watcher_node)
builder.add_node("increment_iteration", increment_iteration)

builder.set_entry_point("architect")

def architect_router(state: AgentState):
    if state.get("current_status") == "error":
        return END
    return "virtuoso"

builder.add_conditional_edges("architect", architect_router, {"virtuoso": "virtuoso", END: END})

# --- Adaptive Hooks (Future-Proofing) ---
ENABLE_ADAPTIVE_FLOW = os.getenv("ENABLE_ADAPTIVE_FLOW", "False").lower() == "true"

def adaptive_virtuoso_exit(state: AgentState):
    """
    Adaptive Hook: Virtuoso -> Sentinel (Default)
    """
    if ENABLE_ADAPTIVE_FLOW:
        print(f"Adaptive Flow: Inspecting Virtuoso output (Mode: {'Active' if ENABLE_ADAPTIVE_FLOW else 'Inactive'})...")
        # Placeholder for future logic:
        # if state.get("confidence") > 0.9: return "watcher"
    
    return "sentinel"

def adaptive_sentinel_exit(state: AgentState):
    """
    Adaptive Hook: Sentinel -> Watcher (Default)
    """
    if ENABLE_ADAPTIVE_FLOW:
        print(f"Adaptive Flow: Inspecting Sentinel output...")
    
    return "watcher"

# Replaces: builder.add_edge("virtuoso", "sentinel")
builder.add_conditional_edges(
    "virtuoso", 
    adaptive_virtuoso_exit, 
    {"sentinel": "sentinel"}
)

# Replaces: builder.add_edge("sentinel", "watcher")
builder.add_conditional_edges(
    "sentinel",
    adaptive_sentinel_exit,
    {"watcher": "watcher"}
)

# Self-Healing Loop
builder.add_conditional_edges(
    "watcher",
    router,
    {
        "virtuoso_fix": "increment_iteration",
        END: END
    }
)

# After incrementing iteration, go back to virtuoso
builder.add_edge("increment_iteration", "virtuoso")

# Compile
use_redis = os.getenv("USE_REDIS_PERSISTENCE", "false").lower() == "true"
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

if use_redis:
    # We use AsyncRedisSaver for production persistence
    checkpointer = AsyncRedisSaver(redis_url)
    print(f"Combinator: Using Redis Persistence ({redis_url})")
else:
    # Default to In-Memory
    checkpointer = InMemorySaver()
    print("Combinator: Using In-Memory Persistence")

graph = builder.compile(checkpointer=checkpointer)
