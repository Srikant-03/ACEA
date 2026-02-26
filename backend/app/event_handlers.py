# Socket.IO Event Handlers
# Imports sio from socket_manager (no circular import)

import asyncio
from datetime import datetime
from app.core.socket_manager import sio

@sio.event
async def connect(sid, environ):
    try:
        print(f"Client connected: {sid}")
    except Exception as e:
        print(f"Connect Error: {e}")

@sio.event
async def disconnect(sid):
    try:
        print(f"Client disconnected: {sid}")
    except Exception as e:
        print(f"Disconnect Error: {e}")


async def _stream_graph_events(sid, graph, initial_state, config, project_id):
    """
    Shared graph streaming logic used by both start_mission and resume_mission.
    
    Handles:
    - Streaming graph events with agent status updates
    - State snapshots for Time Travel
    - Metrics (latency, token estimates, cost)
    - Node-specific logging (architect, virtuoso, sentinel, watcher)
    - Mission completion and VS Code environment setup
    """
    start_time = datetime.now()
    
    async for event in graph.astream(initial_state, config=config):
        for node_name, state_update in event.items():
            agent_name = node_name.upper()
            await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'working'}, room=sid)
            
            # Emit State Snapshot for Time Travel
            if "messages" in state_update:
                safe_state = {
                    "run_id": state_update.get("run_id"),
                    "current_status": node_name,
                    "iteration_count": state_update.get("iteration_count"),
                    "file_system": state_update.get("file_system", {}),
                    "retry_count": state_update.get("retry_count"),
                }
                await sio.emit('state_update', {'state': safe_state}, room=sid)

            # Emit Metrics
            current_time = datetime.now()
            duration = (current_time - start_time).total_seconds() * 1000
            estimated_tokens = len(str(state_update)) // 4
            estimated_cost = (estimated_tokens / 1_000_000) * 0.50
            await sio.emit('metrics', {
                'data': {
                    'steps': state_update.get("iteration_count", 0),
                    'latency': int(duration), 
                    'tokens': estimated_tokens,
                    'cost': round(estimated_cost, 6)
                }
            }, room=sid)

            # Node-specific logging
            if "messages" in state_update:
                last_msg = state_update["messages"][-1]
                await sio.emit('agent_log', {'agent_name': agent_name, 'message': str(last_msg)}, room=sid)
            
            if "blueprint" in state_update and node_name == "architect":
                bp = state_update["blueprint"]
                await sio.emit('agent_log', {'agent_name': agent_name, 'message': f"Blueprint Complete: {bp.get('project_name')}"}, room=sid)
                
            if "file_system" in state_update and node_name == "virtuoso":
                files = state_update["file_system"]
                await sio.emit('agent_log', {'agent_name': agent_name, 'message': f"Generated {len(files)} files."}, room=sid)
                
            if "security_report" in state_update and node_name == "sentinel":
                status = state_update["security_report"].get("status")
                await sio.emit('agent_log', {'agent_name': agent_name, 'message': f"Security Scan: {status}"}, room=sid)

            if "visual_report" in state_update and node_name == "watcher":
                report = state_update["visual_report"]
                status = report.get("status", "UNKNOWN")
                await sio.emit('agent_log', {'agent_name': agent_name, 'message': f"Visual Verification: {status}"}, room=sid)

            # Status: error or success
            if "error" in state_update:
                 await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'error'}, room=sid)
            else:
                 await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'success'}, room=sid)
            
            await asyncio.sleep(0.5) 

    # Mission complete
    await sio.emit('mission_complete', {'project_id': project_id}, room=sid)
    await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': 'Mission Sequence Concluded.'}, room=sid)


async def _setup_vscode_environment(sid, project_id):
    """
    Auto-create VS Code environment after mission completes.
    Extracted from start_mission to avoid duplication.
    """
    try:
        import os
        if not os.getenv("E2B_API_KEY"):
            await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': '⏩ VS Code setup skipped (E2B_API_KEY not configured)'}, room=sid)
            return
        
        await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': '🖥️ Setting up VS Code environment...'}, room=sid)
        
        from app.services.e2b_vscode_service import get_e2b_vscode_service
        from app.core.filesystem import BASE_PROJECTS_DIR
        import json
        from pathlib import Path
        
        # Load blueprint
        blueprint_path = BASE_PROJECTS_DIR / project_id / "blueprint.json"
        blueprint = {}
        if blueprint_path.exists():
            with open(blueprint_path) as f:
                blueprint = json.load(f)
        
        # Create VS Code environment
        vscode_service = get_e2b_vscode_service()
        
        async def progress_callback(msg):
            await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': msg}, room=sid)
        
        result = await vscode_service.create_vscode_environment(
            project_id,
            blueprint,
            on_progress=progress_callback
        )
        
        if result["status"] == "ready":
            await sio.emit('vscode_ready', {
                'project_id': project_id,
                'vscode_url': result['vscode_url'],
                'preview_url': result['preview_url'],
                'sandbox_id': result['sandbox_id'],
                'project_type': result.get('project_type', 'unknown'),
                'port': result.get('port', 3000)
            }, room=sid)
            await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': '✅ VS Code environment ready!'}, room=sid)
        else:
            await sio.emit('vscode_error', {
                'project_id': project_id,
                'error': result.get('message', 'Failed to create VS Code environment')
            }, room=sid)
            await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f"⚠️ VS Code setup failed: {result.get('message', 'Unknown error')}"}, room=sid)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await sio.emit('vscode_error', {
            'project_id': project_id,
            'error': str(e)
        }, room=sid)
        await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f"⚠️ VS Code setup error: {str(e)[:100]}"}, room=sid)


def _enhance_prompt(prompt: str) -> str:
    """
    Enrich sparse user prompts for better project generation.
    Detailed prompts (>40 words or feature-rich) pass through unchanged.
    Short prompts (<15 words) get expanded with structure.
    Medium prompts get light UI/feature hints if missing.
    """
    if not prompt or not prompt.strip():
        return prompt
    
    clean = prompt.strip()
    word_count = len(clean.split())
    
    # Already detailed — don't touch
    if word_count > 40:
        return clean
    
    # Check for architectural signals that suggest a good prompt
    detail_signals = [
        "authentication", "auth", "login", "signup", "register",
        "database", "api", "endpoint", "route", "crud",
        "dashboard", "admin", "panel", "chart", "graph",
        "responsive", "dark mode", "theme", "animation",
        "payment", "stripe", "checkout", "cart",
        "search", "filter", "sort", "pagination",
        "upload", "download", "file", "image",
        "notification", "real-time", "websocket", "chat",
    ]
    
    has_details = sum(1 for s in detail_signals if s in clean.lower())
    
    # Already has enough detail signals
    if has_details >= 3:
        return clean
    
    # SHORT PROMPT: Expand with structure
    if word_count <= 15:
        core = clean
        for prefix in ["build ", "create ", "make ", "generate ", "design ", "i want ", "i need "]:
            if core.lower().startswith(prefix):
                core = core[len(prefix):]
                break
        
        if not core.lower().startswith(("a ", "an ", "the ")):
            core = f"a {core}"
        
        enhanced = (
            f"Build {core} with a clean, modern, responsive UI. "
            f"Include essential features, proper error handling, and intuitive navigation. "
            f"Use a professional color scheme and polished layout."
        )
        return enhanced
    
    # MEDIUM PROMPT: Add light UI hints if missing
    ui_words = ["ui", "design", "theme", "layout", "responsive", "dark", "modern", "clean", "styled"]
    if not any(w in clean.lower() for w in ui_words):
        clean += " Use a clean, modern, responsive UI with professional styling."
    
    return clean


@sio.event
async def start_mission(sid, data):
    """
    Triggered when user clicks 'INITIATE LAUNCH' in War Room.
    Data contains: {'prompt': 'Build a snake game...', 'tech_stack': 'React + Node.js'}
    """
    prompt = data.get('prompt')
    tech_stack = data.get('tech_stack', 'Auto-detect')
    print(f"Mission Start: {prompt} (Stack: {tech_stack})")
    
    # Enhance sparse prompts without over-engineering detailed ones
    enhanced_prompt = _enhance_prompt(prompt)
    if enhanced_prompt != prompt:
        await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f'📝 Prompt enriched for better generation'}, room=sid)
        prompt = enhanced_prompt
    
    await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f'Mission Initiated: "{prompt[:60]}..."'}, room=sid)

    # Initialize Graph State
    initial_state = {
        "messages": [],
        "project_id": f"proj_{int(datetime.now().timestamp())}",
        "agent_id": f"proj_{int(datetime.now().timestamp())}",
        "run_id": sid,
        "user_prompt": prompt,
        "tech_stack": tech_stack,
        "iteration_count": 0,
        "max_iterations": 3,
        "current_status": "planning",
        "file_system": {},
        "errors": [],
        "retry_count": 0
    }
    
    project_id = initial_state['project_id']
    await sio.emit('mission_accepted', {'project_id': project_id}, room=sid)
    
    from app.core.orchestrator import graph
    config = {"configurable": {"thread_id": project_id}}
    
    try:
        await _stream_graph_events(sid, graph, initial_state, config, project_id)
        await _setup_vscode_environment(sid, project_id)
    except Exception as e:
        print(f"Graph Error: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit('mission_error', {'detail': str(e)}, room=sid)


@sio.event
async def resume_mission(sid, data):
    """
    Resume mission from checkpoint.
    Data: {'job_id': 'job_abc123'}
    """
    job_id = data.get('job_id')
    
    if not job_id:
        await sio.emit('mission_error', {'detail': 'job_id required'}, room=sid)
        return
    
    try:
        from app.core.orchestrator import resume_from_checkpoint, graph
        
        state = await resume_from_checkpoint(job_id)
        
        if not state:
            await sio.emit('mission_error', {
                'detail': f'No checkpoint found for {job_id}'
            }, room=sid)
            return
        
        await sio.emit('agent_log', {
            'agent_name': 'SYSTEM',
            'message': f'Resuming from checkpoint: {job_id}'
        }, room=sid)
        
        config = {"configurable": {"thread_id": job_id}}
        
        await _stream_graph_events(sid, graph, state, config, job_id)
        
        # Delete checkpoint on success
        from app.core.persistence import get_checkpoint_manager
        from app.core.config import settings
        manager = get_checkpoint_manager(settings.REDIS_URL)
        await manager.delete_checkpoint(job_id)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await sio.emit('mission_error', {'detail': str(e)}, room=sid)
