import uvicorn
import os
import sys
import subprocess

# Define path to venv python
VENV_PYTHON = os.path.join(os.path.dirname(__file__), "backend", "venv", "Scripts", "python.exe")

def is_venv():
    return (hasattr(sys, 'real_prefix') or
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))

if __name__ == "__main__":
    # 1. Auto-Activate Logic
    if not is_venv():
        if os.path.exists(VENV_PYTHON):
            print("🔄 Switching to Virtual Environment...")
            # Re-run this script with the venv python
            subprocess.call([VENV_PYTHON] + sys.argv)
            sys.exit()
        else:
            print("⚠️ Warning: Virtual environment not found at backend/venv. Running with system Python.")

    # 2. Start Server
    print("🚀 Starting ACEA Sentinel Backend...")
    print(f"🐍 Python: {sys.executable}")
    
    # Ensure backend is in path
    sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
    
    uvicorn.run(
        "backend.app.main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir="."
    )
