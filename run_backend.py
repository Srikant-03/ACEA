import uvicorn
import os
import sys
import subprocess
import platform

# Define path to venv python
def get_venv_python():
    is_windows = platform.system() == "Windows"
    base_dir = os.path.dirname(__file__)
    if is_windows:
        return os.path.join(base_dir, "backend", "venv", "Scripts", "python.exe")
    else:
        return os.path.join(base_dir, "backend", "venv", "bin", "python")

VENV_PYTHON = get_venv_python()

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
            print(f"⚠️ Warning: Virtual environment not found at {VENV_PYTHON}. Running with system Python.")

    # 2. Fix Windows Asyncio Loop
    # Windows default ProactorEventLoop is required for Playwright subprocesses.
    # Previous attempt to use SelectorEventLoop caused NotImplementedError.
    # We revert to default behavior.
    if sys.platform == 'win32':
        # Ensure we are using Proactor (default in 3.12, but being explicit doesn't hurt if issues persist)
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # 3. Start Server
    print("🚀 Starting ACEA Sentinel Backend...")
    print(f"🐍 Python: {sys.executable}")
    
    # Ensure backend is in path
    sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
    
    uvicorn.run(
        "backend.app.main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"],
        app_dir=".",
        log_level="warning",
        access_log=False,
        loop="asyncio"  # FORCE use of standard asyncio loop (Proactor on Windows)
    )
