from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from datetime import datetime


# Initialize FastAPI app
app = FastAPI(
    title="ACEA Sentinel API",
    description="Backend API for ACEA Sentinel Autonomous Software Engineering Platform",
    version="1.0.0"
)

# Configure CORS
origins = [
    "http://localhost:3000",  # Next.js frontend
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Socket.IO
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=origins
)
socket_app = socketio.ASGIApp(sio, app)

# CRITICAL: Initialize SocketManager with sio instance
from app.core.socket_manager import SocketManager
sm = SocketManager()
sm.set_server(sio)

from contextlib import asynccontextmanager
from app.core.database import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create DB tables
    create_db_and_tables()
    yield
    # Shutdown logic if needed

# Re-initialize FastAPI app with lifespan
app = FastAPI(
    title="ACEA Sentinel API",
    description="Backend API for ACEA Sentinel Autonomous Software Engineering Platform",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: Real System Health
try:
    import psutil
except ImportError:
    psutil = None
    print("Warning: 'psutil' module not found. System health stats will be disabled.")

import asyncio

@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(broadcast_system_health())

async def broadcast_system_health():
    while True:
        if psutil:
            try:
                cpu = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory().percent
                
                await sio.emit('system_health', {
                    'cpu': cpu, 
                    'memory': memory,
                    'status': 'OPERATIONAL'
                })
            except Exception:
                pass
        else:
             # Basic heartbeat if psutil is missing
             await sio.emit('system_health', {'status': 'LIMITED_MODE'})
             
        await asyncio.sleep(2)

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def start_mission(sid, data):
    """
    Triggered when user clicks 'INITIATE LAUNCH' in War Room.
    Data contains: {'prompt': 'Build a snake game...'}
    """
    prompt = data.get('prompt')
    print(f"Mission Start: {prompt}")
    
    # 1. Notify: Mission Initialized
    await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': f'Mission Initiated: "{prompt[:40]}..."'}, room=sid)

    # 2. Initialize Graph State
    initial_state = {
        "messages": [],
        "project_id": f"proj_{int(datetime.now().timestamp())}",
        "user_prompt": prompt,
        "iteration_count": 0,
        "max_iterations": 3,
        "current_status": "planning",
        "file_system": {},
        "errors": []
    }
    
    # Notify Frontend of Project ID immediately so it can prepare the IDE
    await sio.emit('mission_accepted', {'project_id': initial_state['project_id']}, room=sid)
    
    # 3. Import Graph
    # We import inside function to avoid circular imports during startup if any
    from app.orchestrator import graph
    
    config = {"configurable": {"thread_id": sid}}
    
    # 4. Run Graph Stream
    try:
        async for event in graph.astream(initial_state, config=config):
            # event is a dict of the node name and the state update
            for node_name, state_update in event.items():
                
                # Update Status on Frontend
                agent_name = node_name.upper()
                await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'working'}, room=sid)
                
                # Parse specific updates to log
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
                    # Emit specific message based on status
                    await sio.emit('agent_log', {'agent_name': agent_name, 'message': f"Visual Verification: {status}"}, room=sid)

                # Mark as success after node finishes (conceptually)
                await sio.emit('agent_status', {'agent_name': agent_name, 'status': 'idle'}, room=sid)

        # Check final status from the graph execution
        # Note: We need to capture the final state. 'event' in the loop is the delta.
        # We can track 'current_status' from the last event updates.
        
        # A simple heuristic: If the last log was an error or if we returned early?
        # Better: We can't easily see the final state object here without accumulating it.
        # But we can rely on the last message or status emitted.
        
        # Let's emit a specific 'mission_finished' with the success/fail flag.
        # But to be robust, let's just emit 'mission_complete' ONLY if we didn't crash.
        
        await sio.emit('mission_complete', {'project_id': initial_state['project_id']}, room=sid)
        await sio.emit('agent_log', {'agent_name': 'SYSTEM', 'message': 'Mission Sequence Concluded.'}, room=sid)

    except Exception as e:
        print(f"Graph Error: {e}")
        await sio.emit('mission_error', {'detail': str(e)}, room=sid)

from fastapi.staticfiles import StaticFiles
import os

# Create generated_projects dir if it doesn't exist
# Move up 3 levels from app/main.py -> backend -> ACEA -> generated_projects
PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "generated_projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# Mount the Generated Projects directory to be served at /preview
app.mount("/preview", StaticFiles(directory=PROJECTS_DIR, html=True), name="preview")

@app.get("/")
async def root():
    return {"message": "ACEA Sentinel System Online", "status": "active"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "services": {"database": "unknown", "redis": "unknown"}}

# To run: uvicorn app.main:socket_app --reload
