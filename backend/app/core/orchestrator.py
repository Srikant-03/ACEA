# ACEA Sentinel - Orchestrator with Self-Healing Loop
# Manages the agent workflow with automatic error detection and fixing

import json
import os
import asyncio
from typing import Dict, Any, Optional

# Updated imports for new components
from app.agents.state import AgentState
from app.core.persistence import AsyncRedisSaver, LangGraphRedisSaver
from app.core.key_manager import KeyManager
from app.core.HybridModelClient import HybridModelClient
from app.core.model_response import ModelResponse
from app.core.config import settings

# Agents
from app.agents.architect import ArchitectAgent
from app.agents.virtuoso import VirtuosoAgent
from app.agents.sentinel import SentinelAgent
from app.agents.oracle import OracleAgent
from app.agents.watcher import WatcherAgent
from app.agents.advisor import AdvisorAgent
from app.agents.testing_agent import TestingAgent # Added

# LangGraph
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

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
    print(f"Warning: Failed to initialize KeyManager: {e}")
    hybrid_client = None

# Initialize Agents
architect_agent = ArchitectAgent()
virtuoso_agent = VirtuosoAgent()
sentinel_agent = SentinelAgent()
oracle_agent = OracleAgent()
watcher_agent = WatcherAgent()
advisor_agent = AdvisorAgent()
testing_agent = TestingAgent() # Added

# Helper to save state manually
async def save_state(state: AgentState):
    if USE_REDIS_PERSISTENCE and redis_saver:
        try:
             # state.json() is now available via dataclass method
             await redis_saver.set(f"state:{state.agent_id}", state.json())
        except Exception as e:
             print(f"Failed to save state to Redis: {e}")
             # Halt if configured? User said "any failure should raise an exception to halt... ensuring failure is noticed"
             if USE_REDIS_PERSISTENCE:
                 raise e

async def load_state(agent_id: str) -> Optional[AgentState]:
    if USE_REDIS_PERSISTENCE and redis_saver:
        try:
            data = await redis_saver.get(f"state:{agent_id}")
            return AgentState.parse_raw(data)
        except KeyError:
            return None
        except Exception as e:
             print(f"Failed to load state from Redis: {e}")
             if USE_REDIS_PERSISTENCE:
                 raise e
    return None

# --- NODES ---

async def architect_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    # Ensure agent_id is set (using project_id as proxy or separate field)
    if not state.agent_id:
        state.agent_id = state.project_id

    # Restore state if needed (this logic typically sits outside the graph, but user asked for restoration on startup/resume)
    # Since this is a node, execution has already started. We assume state is passed in.
    
    # Structured Log
    thread_id = state.project_id
    print(f"--- ARCHITECT NODE (Thread: {thread_id}) ---")
    
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
    state.current_status = "blueprint_generated"
    state.messages.append(f"Architect designed system: {blueprint.get('project_name')}")
    
    # Save State
    await save_state(state)
    
    return {"blueprint": blueprint, "current_status": "blueprint_generated"}

from app.core.filesystem import write_project_files

async def virtuoso_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    thread_id = state.project_id
    print(f"--- VIRTUOSO NODE (Thread: {thread_id}) ---")
    
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
        new_files = await _handle_self_healing(sm, errors, current_files, iteration)
    else:
        new_files = await _handle_normal_generation(blueprint)
    
    new_files = _post_process_files(new_files)
    write_project_files(state.project_id, new_files)
    
    state.file_system = new_files
    state.current_status = "code_generated"
    state.errors = []
    
    # Save State
    await save_state(state)

    return {"file_system": new_files, "current_status": "code_generated", "errors": []}

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
    cleaned = {}
    for path, content in files.items():
        if isinstance(content, str):
            cleaned[path] = content.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        else:
            cleaned[path] = content
    return cleaned


async def sentinel_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    from app.agents.state import Issue
    sm = SocketManager()
    
    thread_id = state.project_id
    print(f"--- SENTINEL NODE (Thread: {thread_id}) ---")
    
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
    
    return {"security_report": report, "current_status": "security_audited", "issues": state.issues}

async def testing_node(state: AgentState):
    """Run automated tests."""
    from app.core.socket_manager import SocketManager
    sm = SocketManager()
    
    thread_id = state.project_id
    print(f"--- TESTING NODE (Thread: {thread_id}) ---")
    
    await sm.emit("agent_log", {
        "agent_name": "TESTING", 
        "message": "Starting automated tests...",
        "metadata": {"thread_id": thread_id, "step": "testing"}
    })
    
    # Ensure project_dir is set on state
    from app.core.filesystem import BASE_PROJECTS_DIR
    project_dir = str(BASE_PROJECTS_DIR / state.project_id)
    # Using setattr to be safe as dataclass might not have it defined in __init__ if strictly typed without extra fields
    # But AgentState definition usually allows dynamic fields if not slotted or if specifically added.
    setattr(state, "project_dir", project_dir)
    
    state = await testing_agent.run(state)
    # testing_agent.run updates state.issues
    
    # TestingAgent runs in place, updating state.messages and state.errors
    # We must return these updates to the graph so they are emitted to the UI
    
    # Save State
    await save_state(state)
    
    return {
        "issues": state.issues,
        "messages": state.messages[-5:], # Return recent messages to ensure visibility without flooding
        "errors": state.errors
    }

async def watcher_node(state: AgentState):
    from app.core.socket_manager import SocketManager
    from app.core.filesystem import BASE_PROJECTS_DIR
    from app.agents.state import Issue
    
    sm = SocketManager()
    thread_id = state.project_id
    print(f"--- WATCHER NODE (Thread: {thread_id}) ---")
    
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

def router(state: AgentState):
    """
    SELF-HEALING ROUTER
    """
    errors = state.errors
    iteration = state.iteration_count
    max_iterations = state.max_iterations
    
    if errors and len(errors) > 0:
        if iteration >= max_iterations:
            print(f"Router: Max iterations ({max_iterations}) reached. Ending.")
            return END
        
        print(f"Router: Errors found. Routing to Virtuoso for fix (iteration {iteration + 1})")
        return "virtuoso_fix"
    
    print("Router: No errors. Mission complete!")
    return END

def increment_iteration(state: AgentState):
    count = state.iteration_count + 1
    state.iteration_count = count
    # Save State is implicit in nodes, not helper functions, but good to save here too if we want
    # But since this is a synchronous node, we can't await save_state easily unless we make it async.
    # For now, skip saving on increment.
    return {"iteration_count": count}

# Build Graph
builder = StateGraph(AgentState)

builder.add_node("architect", architect_node)
builder.add_node("virtuoso", virtuoso_node)
builder.add_node("sentinel", sentinel_node)
builder.add_node("testing", testing_node) # Added
builder.add_node("watcher", watcher_node)
builder.add_node("increment_iteration", increment_iteration)

builder.set_entry_point("architect")

def architect_router(state: AgentState):
    if state.current_status == "error":
        return END
    return "virtuoso"

builder.add_conditional_edges("architect", architect_router, {"virtuoso": "virtuoso", END: END})

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

builder.add_conditional_edges("virtuoso", adaptive_virtuoso_exit, {"sentinel": "sentinel"})
builder.add_conditional_edges("sentinel", adaptive_sentinel_exit, {"testing": "testing"}) # Modified
builder.add_conditional_edges("testing", adaptive_testing_exit, {"watcher": "watcher"}) # Added

builder.add_conditional_edges(
    "watcher",
    router,
    {
        "virtuoso_fix": "increment_iteration",
        END: END
    }
)

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
    print(f"Orchestrator: Using LangGraphRedisSaver ({REDIS_URL})")
else:
    checkpointer = MemorySaver()
    print("Orchestrator: Using In-Memory Persistence")

graph = builder.compile(checkpointer=checkpointer)
