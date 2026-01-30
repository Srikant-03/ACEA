#!/bin/bash

# ACEA Startup Script for macOS/Linux

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting ACEA Sentinel Setup & Run...${NC}"

# 1. Check Pre-requisites
echo -e "${BLUE}🔍 Checking requirements...${NC}"
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed."
    exit 1
fi
if ! command -v npm &> /dev/null; then
    echo "Node.js (npm) is required but not installed."
    exit 1
fi

# 2. Backend Setup
echo -e "${BLUE}🐍 Setting up Backend...${NC}"
cd backend || exit

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "Installing/Updating backend dependencies..."
pip install -r requirements.txt
cd ..

# 3. Frontend Setup
echo -e "${BLUE}⚛️ Setting up Frontend...${NC}"
cd frontend || exit
echo "Installing frontend dependencies..."
npm install
cd ..

# 4. Start Services
echo -e "${GREEN}✅ Setup complete! Starting services...${GREEN}"

# Function to kill child processes on exit
cleanup() {
    echo -e "${BLUE}🛑 Shutting down services...${NC}"
    kill $(jobs -p)
    exit
}
trap cleanup SIGINT

# Start Backend
echo -e "${BLUE}🚀 Starting Backend Server...${NC}"
python3 run_backend.py &
BACKEND_PID=$!

# Start Frontend
echo -e "${BLUE}🚀 Starting Frontend Server...${NC}"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo -e "${GREEN}✨ ACEA is running!${NC}"
echo -e "   Frontend: http://localhost:3000"
echo -e "   Backend:  http://localhost:8000"
echo -e "${BLUE}Press Ctrl+C to stop all services${NC}"

wait
