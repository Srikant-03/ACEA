@echo off
TITLE ACEA SENTINEL LAUNCHER
COLOR 0A

echo.
echo  ===========================================================
echo       _    ____ _____    _      ____  _____ _   _ _____ 
echo      / \  / ___| ____|  / \    / ___|| ____| \ | |_   _|
echo     / _ \| |   |  _|   / _ \   \___ \|  _| |  \| | | |  
echo    / ___ \ |___| |___ / ___ \   ___) | |___| |\  | | |  
echo   /_/   \_\____|_____/_/   \_\ |____/|_____|_| \_| |_|  
echo.
echo              AUTONOMOUS   CODE   PLATFORM
echo  ===========================================================
echo.

:: ─────────────────────────────────────────────────────────
:: Pre-flight checks
:: ─────────────────────────────────────────────────────────

:: Check for .env
if not exist "backend\.env" (
    echo  [ERROR] backend\.env file not found!
    echo  Please create it using backend\.env.example
    echo.
    pause
    exit /b 1
)

:: Check for venv
if not exist "backend\venv\Scripts\activate.bat" (
    echo  [ERROR] Virtual environment not found at backend\venv
    echo  Run: python -m venv backend\venv
    echo.
    pause
    exit /b 1
)

:: Check for node_modules
if not exist "frontend\node_modules" (
    echo  [WARN] frontend\node_modules not found. Running npm install...
    cd frontend && npm install && cd ..
)

:: ─────────────────────────────────────────────────────────
:: Launch Backend (FastAPI + Uvicorn)
:: ─────────────────────────────────────────────────────────
echo  [1/3] Starting Backend Server (FastAPI on :8000)...
start "ACEA Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\activate && uvicorn app.main:socket_app --host 0.0.0.0 --port 8000 --reload"

:: ─────────────────────────────────────────────────────────
:: Launch Frontend (Next.js)
:: ─────────────────────────────────────────────────────────
echo  [2/3] Starting Frontend Server (Next.js on :3000)...
start "ACEA Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

:: ─────────────────────────────────────────────────────────
:: Open Dashboard
:: ─────────────────────────────────────────────────────────
echo  [3/3] Opening Dashboard in 5 seconds...
timeout /t 5 >nul
start http://localhost:3000

echo.
echo  ===========================================================
echo       ALL SYSTEMS ONLINE. DASHBOARD LAUNCHED.
echo  ===========================================================
echo.
echo  Backend:   http://localhost:8000
echo  Frontend:  http://localhost:3000
echo  API Docs:  http://localhost:8000/docs
echo.
echo  Press any key to close this launcher window.
echo  (Backend ^& Frontend will keep running in their own windows)
echo.
pause >nul
