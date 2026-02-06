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

# Configure CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import sio from socket_manager (no circular import)
from app.core.socket_manager import sio

# Import event handlers to register them with sio
# This import has NO circular dependency now because event_handlers imports sio from socket_manager, not from here
from app import event_handlers

# Include API Router
from app.api import endpoints
fastapi_app.include_router(endpoints.router, prefix="/api")

# Mount Static Files (Generated Projects)
from fastapi.staticfiles import StaticFiles
import os

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
    return {"message": "ACEA Sentinel System Online", "status": "active"}

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy", "services": {"database": "unknown", "redis": "unknown"}}


