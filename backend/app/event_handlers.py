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

@sio.event
async def start_mission(sid, data):
    """
    Triggered when user clicks 'INITIATE LAUNCH' in War Room.
    Data contains: {'prompt': 'Build a snake game...', 'tech_stack': 'React + Node.js'}
    """
    prompt = data.get('prompt')
    tech_stack = data.get('tech_stack', 'Auto-detect')
    print(f"Mission Start: {prompt} (Stack: {tech_stack})")
    
    # 1. Notify: Mission Initialized
    await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f'Mission Initiated: "{prompt[:40]}..."'}, room=sid)

    # 2. Initialize Graph State
    initial_state = {
        "messages": [],
        "project_id": f"proj_{int(datetime.now().timestamp())}",
        "agent_id": f"proj_{int(datetime.now().timestamp())}", # Initialize agent_id with project_id
        "run_id": sid, # Use Socket ID as Run ID for tracing
        "user_prompt": prompt,
        "tech_stack": tech_stack,
        "iteration_count": 0,
        "max_iterations": 3,
        "current_status": "planning",
        "file_system": {},
        "errors": [],
        "retry_count": 0
    }
    
    # Notify Frontend of Project ID immediately so it can prepare the IDE
    await sio.emit('mission_accepted', {'project_id': initial_state['project_id']}, room=sid)
    
    # 3. Import Graph (lazy to avoid circular imports at module load time)
    from app.core.orchestrator import graph
    
    # Use PROJECT ID as Thread ID for restart-safe persistence
    config = {"configurable": {"thread_id": initial_state['project_id']}}
    
    # 4. Run Graph Stream
    try:
        start_time = datetime.now()
        async for event in graph.astream(initial_state, config=config):
            for node_name, state_update in event.items():
                agent_name = node_name.upper()
                await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'working'}, room=sid)
                
                # Emit State Snapshot for Time Travel
                if "messages" in state_update:
                    # Sanitize state for frontend
                    safe_state = {
                        "run_id": state_update.get("run_id"),
                        "current_status": node_name,
                        "iteration_count": state_update.get("iteration_count"),
                        "file_system": state_update.get("file_system", {}),
                        "retry_count": state_update.get("retry_count"),
                        # Don't send full message history if huge, but for now it's fine
                        # "messages": [str(m) for m in state_update.get("messages", [])] 
                    }
                    await sio.emit('state_update', {'state': safe_state}, room=sid)

                # Emit Metrics
                current_time = datetime.now()
                duration = (current_time - start_time).total_seconds() * 1000
                await sio.emit('metrics', {
                    'data': {
                        'steps': state_update.get("iteration_count", 0),
                        'latency': int(duration), 
                        'tokens': len(str(state_update)) // 4, # Rough estimate
                        'cost': 0.0 # Placeholder
                    }
                }, room=sid)

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

                # Refined Status Logic: Don't just reset to idle
                if "error" in state_update:
                     await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'error'}, room=sid)
                else:
                     await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'success'}, room=sid)
                
                # Small delay to let the "Success" state match the visual pulse before next node or idle
                await asyncio.sleep(0.5) 
                # await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'idle'}, room=sid) # Optional: keep success state until next run?

        await sio.emit('mission_complete', {'project_id': initial_state['project_id']}, room=sid)
        await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': 'Mission Sequence Concluded.'}, room=sid)
        
        # Auto-create VS Code environment after mission completes
        try:
            await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': '🖥️ Setting up VS Code environment...'}, room=sid)
            
            from app.services.e2b_vscode_service import get_e2b_vscode_service
            from app.core.filesystem import read_project_files
            import json
            from pathlib import Path
            
            # Load blueprint
            from app.core.filesystem import BASE_PROJECTS_DIR
            blueprint_path = BASE_PROJECTS_DIR / initial_state['project_id'] / "blueprint.json"
            blueprint = {}
            if blueprint_path.exists():
                with open(blueprint_path) as f:
                    blueprint = json.load(f)
            
            # Create VS Code environment
            vscode_service = get_e2b_vscode_service()
            
            async def progress_callback(msg):
                await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': msg}, room=sid)
            
            result = await vscode_service.create_vscode_environment(
                initial_state['project_id'],
                blueprint,
                on_progress=progress_callback
            )
            
            if result["status"] == "ready":
                await sio.emit('vscode_ready', {
                    'project_id': initial_state['project_id'],
                    'vscode_url': result['vscode_url'],
                    'preview_url': result['preview_url'],
                    'sandbox_id': result['sandbox_id'],
                    'project_type': result.get('project_type', 'unknown'),
                    'port': result.get('port', 3000)
                }, room=sid)
                await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': '✅ VS Code environment ready!'}, room=sid)
            else:
                await sio.emit('vscode_error', {
                    'project_id': initial_state['project_id'],
                    'error': result.get('message', 'Failed to create VS Code environment')
                }, room=sid)
                await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f"⚠️ VS Code setup failed: {result.get('message', 'Unknown error')}"}, room=sid)
        except Exception as e:
            import traceback
            traceback.print_exc()
            await sio.emit('vscode_error', {
                'project_id': initial_state['project_id'],
                'error': str(e)
            }, room=sid)
            await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f"⚠️ VS Code setup error: {str(e)[:100]}"}, room=sid)

    except Exception as e:
        print(f"Graph Error: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit('mission_error', {'detail': str(e)}, room=sid)
