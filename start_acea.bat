@echo off
TITLE ACEA SENTINEL LAUNCHER

echo ==================================================
echo       ACEA SENTINEL - AUTONOMOUS PLATFORM
echo ==================================================
echo.

:: Check for .env
if not exist "backend\.env" (
    echo [ERROR] backend\.env file not found!
    echo Please create it using backend\.env.example
    pause
    exit
)

echo [1/3] Starting Backend Server (FastAPI)...
start "ACEA Backend" cmd /k "cd backend && venv\Scripts\activate && uvicorn app.main:socket_app --host 0.0.0.0 --port 8000 --reload"

echo [2/3] Starting Frontend Server (Next.js)...
start "ACEA Frontend" cmd /k "cd frontend && npm run dev"

echo [3/3] Opening Dashboard...
timeout /t 5 >nul
start http://localhost:3000

echo.
echo ==================================================
echo       ALL SYSTEMS GO. ACCESSING WAR ROOM.
echo ==================================================
echo.
pause
