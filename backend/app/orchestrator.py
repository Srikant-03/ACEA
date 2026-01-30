# ACEA Sentinel - Orchestrator with Self-Healing Loop
# Manages the agent workflow with automatic error detection and fixing

import json
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.agents.state import AgentState
from app.agents.architect import ArchitectAgent
from app.agents.virtuoso import VirtuosoAgent
from app.agents.sentinel import SentinelAgent
from app.agents.oracle import OracleAgent
from app.agents.watcher import WatcherAgent
from app.agents.advisor import AdvisorAgent

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
    
    print("--- ARCHITECT NODE ---")
    await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "Architect analyzing requirements..."})
    
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
    
    print("--- VIRTUOSO NODE ---")
    await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "Entering Virtuoso Node..."})
    
    blueprint = state["blueprint"]
    if not blueprint:
        await sm.emit("agent_log", {"agent_name": "SYSTEM", "message": "ERROR: Blueprint is missing!"})
        return {"current_status": "error", "errors": ["Missing Blueprint"]}

    errors = state.get("errors", [])
    current_files = state.get("file_system", {})
    iteration = state.get("iteration_count", 0)
    
    if errors and iteration > 0:
        # SELF-HEALING MODE: Regenerate with error context
        await sm.emit("agent_log", {"agent_name": "VIRTUOSO", "message": f"🔧 Self-Healing Mode: Fixing {len(errors)} errors (Iteration {iteration})..."})
        new_files = await virtuoso_agent.generate_from_blueprint(blueprint, existing_files=current_files, errors=errors)
    else:
        # Normal generation
        new_files = await virtuoso_agent.generate_from_blueprint(blueprint)
    
    # FIX: Unescape newlines in generated code (JSON batch generation returns escaped strings)
    for path in new_files:
        if isinstance(new_files[path], str):
            new_files[path] = new_files[path].replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    
    # PERSIST TO DISK
    project_path = write_project_files(state["project_id"], new_files)
    
    return {
        "file_system": new_files,
        "current_status": "code_generated",
        "messages": [f"Virtuoso generated {len(new_files)} files"],
        "errors": []  # Clear errors after regeneration
    }

async def sentinel_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    print("--- SENTINEL NODE ---")
    await sm.emit("agent_log", {"agent_name": "SENTINEL", "message": "Initiating security scan..."})
    
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
    print("--- WATCHER NODE ---")
    
    project_id = state["project_id"]
    project_path = str(BASE_PROJECTS_DIR / project_id)
    
    await sm.emit("agent_log", {"agent_name": "WATCHER", "message": "Starting project verification..."})
    
    try:
        # Use quick_verify for faster feedback (no server startup)
        # For full browser testing, use: run_and_verify_project(project_path, project_id)
        report = await watcher_agent.quick_verify(project_id)
        
        if report["status"] == "FAIL":
            await sm.emit("agent_log", {"agent_name": "WATCHER", "message": f"❌ Verification failed: {len(report['errors'])} errors found"})
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

builder.add_edge("virtuoso", "sentinel")
builder.add_edge("sentinel", "watcher")

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
memory = MemorySaver()
graph = builder.compile(checkpointer=memory)
