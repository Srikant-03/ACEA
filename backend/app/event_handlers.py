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
        "user_prompt": prompt,
        "tech_stack": tech_stack,
        "iteration_count": 0,
        "max_iterations": 3,
        "current_status": "planning",
        "file_system": {},
        "errors": []
    }
    
    # Notify Frontend of Project ID immediately so it can prepare the IDE
    await sio.emit('mission_accepted', {'project_id': initial_state['project_id']}, room=sid)
    
    # 3. Import Graph (lazy to avoid circular imports at module load time)
    from app.orchestrator import graph
    
    config = {"configurable": {"thread_id": sid}}
    
    # 4. Run Graph Stream
    try:
        async for event in graph.astream(initial_state, config=config):
            for node_name, state_update in event.items():
                agent_name = node_name.upper()
                await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'working'}, room=sid)
                
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

                await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'idle'}, room=sid)

        await sio.emit('mission_complete', {'project_id': initial_state['project_id']}, room=sid)
        await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': 'Mission Sequence Concluded.'}, room=sid)

    except Exception as e:
        print(f"Graph Error: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit('mission_error', {'detail': str(e)}, room=sid)
