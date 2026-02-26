# Fix Windows event loop BEFORE any async imports.
# uvicorn reload=True spawns child processes that lose the policy set in run_backend.py.
# Playwright requires ProactorEventLoop for subprocess creation on Windows.
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Load environment variables from .env first
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from contextlib import asynccontextmanager
from app.core.database import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create DB tables
    create_db_and_tables()
    yield
    # Shutdown logic if needed

# Initialize FastAPI app
fastapi_app = FastAPI(
    title="ACEA Sentinel API",
    description="Backend API for ACEA Sentinel Autonomous Software Engineering Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS — works for both local dev and production
import os

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Add production frontend URL if set (e.g. https://your-app.vercel.app)
frontend_url = os.getenv("FRONTEND_URL", "")
if frontend_url:
    origins.append(frontend_url)
    # Also allow the bare domain without trailing slash
    if frontend_url.endswith("/"):
        origins.append(frontend_url.rstrip("/"))

# On Railway / production, also allow all Vercel preview URLs
environment = os.getenv("ENVIRONMENT", "development")
if environment == "production":
    # Vercel preview deployments use random subdomains
    origins.append("https://*.vercel.app")

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Allow regex pattern for Vercel preview deployments in production
    allow_origin_regex=r"https://.*\.vercel\.app" if environment == "production" else None,
)

# Import sio from socket_manager (no circular import)
from app.core.socket_manager import sio

# Import event handlers to register them with sio
# This import has NO circular dependency now because event_handlers imports sio from socket_manager, not from here
from app import event_handlers

# Include API Router
from app.api import endpoints
fastapi_app.include_router(endpoints.router, prefix="/api")

# Mount Static Files (Generated Projects) — works on both local and Railway
from fastapi.staticfiles import StaticFiles

PROJECTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "generated_projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)
fastapi_app.mount("/preview", StaticFiles(directory=PROJECTS_DIR, html=True), name="preview")

# Mount Screenshots for Visual Verification
SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
fastapi_app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")

# Finalize Socket App - Wrap FastAPI with Socket.IO
# This ensures socket.io paths are handled first
app = socketio.ASGIApp(sio, fastapi_app)

# Health endpoints need to be attached to the inner FastAPI app
@fastapi_app.get("/")
async def root():
    return {"message": "ACEA Sentinel System Online", "status": "active", "environment": environment}

@fastapi_app.get("/health")
async def health_check():
    redis_status = "disabled"
    db_status = "active"
    
    if os.getenv("USE_REDIS_PERSISTENCE", "false").lower() == "true":
         try:
             import redis.asyncio as redis
             url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
             client = redis.from_url(url, socket_connect_timeout=1)
             await client.ping()
             await client.close()
             redis_status = "connected"
         except Exception as e:
             redis_status = f"error: {str(e)}"

    return {
        "status": "healthy", 
        "environment": environment,
        "services": {
            "database": db_status, 
            "redis": redis_status
        }
    }
