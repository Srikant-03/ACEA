# 🚀 ACEA Sentinel

**Autonomous Codebase Enhancement Agent** - An AI-powered autonomous software development platform that designs, generates, tests, and self-heals code.

![ACEA Banner](docs/banner.png)

## ✨ Features

- **🏗️ Architect Agent** - Designs system architecture from natural language prompts
- **💻 Virtuoso Agent** - Generates production-ready code in batches  
- **🛡️ Sentinel Agent** - Scans for security vulnerabilities
- **👁️ Watcher Agent** - Validates generated code and triggers self-healing
- **🔄 Self-Healing Loop** - Automatically fixes errors and regenerates code
- **☁️ + 🏠 Hybrid AI** - Uses Gemini API with automatic Ollama local model fallback

## 🖥️ System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | 8GB VRAM | 12GB+ VRAM (RTX 3060+) |
| **RAM** | 16GB | 32GB |
| **CPU** | 8 cores | 16+ cores |
| **Storage** | 20GB free | 50GB free |

## 📦 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/saumya-200/ACEA-A-Checkpointed-Agentic-System-for-Long-Horizon-Autonomous-Codebase-Improvement.git
cd ACEA-A-Checkpointed-Agentic-System-for-Long-Horizon-Autonomous-Codebase-Improvement
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Frontend Setup

```bash
cd frontend
npm install
```

### 4. Environment Configuration

Create `backend/.env` file:

```env
# Gemini API Keys (get from https://aistudio.google.com/apikey)
GEMINI_API_KEYS="your_api_key_1,your_api_key_2"

# Database
DATABASE_URL=sqlite:///./acea.db

# Security
JWT_SECRET="your-secret-key-here"
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### 5. (Optional) Local Model Setup with Ollama

For unlimited local inference when API quotas are exhausted:

```bash
# Install Ollama
winget install Ollama.Ollama  # Windows
# or download from https://ollama.com/download

# Start Ollama server
ollama serve

# Pull the coding model (~9GB)
ollama pull qwen2.5-coder:14b
```

## 🚀 Running the Application

### Start Backend Server

```bash
cd backend
python run_backend.py
```

Backend will be available at: `http://localhost:8000`

### Start Frontend Development Server

```bash
cd frontend
npm run dev
```

Frontend will be available at: `http://localhost:3000`

## 🎮 Usage

1. Open `http://localhost:3000` in your browser
2. Navigate to the **War Room** dashboard
3. Enter a prompt like: *"Create a tic-tac-toe game"*
4. Watch the agents work in real-time!

### Example Prompts

- "Make a simple todo app with task management"
- "Create a weather dashboard with API integration"
- "Build an e-commerce product page with cart functionality"

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      ACEA SENTINEL CORE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   User Prompt                                                   │
│        ↓                                                        │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │Architect │───▶│Virtuoso  │───▶│Sentinel  │───▶│ Watcher  │ │
│   │(Design)  │    │(Generate)│    │(Security)│    │(Verify)  │ │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│                        ▲                               │        │
│                        │         Self-Healing          │        │
│                        └───────────────────────────────┘        │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                 Hybrid Model Client                      │  │
│   │   Gemini API (Primary) ──▶ Ollama Local (Fallback)      │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
ACEA/
├── backend/
│   ├── app/
│   │   ├── agents/           # AI Agents
│   │   │   ├── architect.py  # System design
│   │   │   ├── virtuoso.py   # Code generation
│   │   │   ├── sentinel.py   # Security scanning
│   │   │   ├── watcher.py    # Visual verification
│   │   │   └── state.py      # Agent state management
│   │   ├── core/
│   │   │   ├── config.py     # Configuration
│   │   │   ├── key_manager.py# API key rotation
│   │   │   ├── local_model.py# Ollama integration
│   │   │   └── socket_manager.py
│   │   └── api/
│   │       └── endpoints.py  # REST API routes
│   ├── orchestrator.py       # LangGraph workflow
│   └── main.py               # FastAPI entry point
├── frontend/
│   ├── src/
│   │   └── app/
│   │       ├── page.tsx      # Landing page
│   │       └── war-room/
│   │           └── page.tsx  # Main dashboard
│   └── package.json
└── README.md
```

## 🔧 Configuration Options

### API Key Rotation

Add multiple API keys for automatic rotation on rate limits:

```env
GEMINI_API_KEYS="key1,key2,key3,key4,key5"
```

### Local Model Options

| Model | VRAM | Quality | Command |
|-------|------|---------|---------|
| qwen2.5-coder:14b | 10GB | ⭐⭐⭐⭐⭐ | `ollama pull qwen2.5-coder:14b` |
| qwen2.5-coder:7b | 6GB | ⭐⭐⭐⭐ | `ollama pull qwen2.5-coder:7b` |
| codellama:13b | 8GB | ⭐⭐⭐ | `ollama pull codellama:13b` |

## 🛠️ Tech Stack

**Backend:**
- Python 3.12
- FastAPI
- LangGraph
- Google Generative AI SDK
- Ollama (Local Models)
- Socket.IO

**Frontend:**
- Next.js 15
- React
- Tailwind CSS 4
- TypeScript
- Lucide Icons

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## 📧 Contact

- **Author**: Srikant
- **GitHub**: [@Srikant-03](https://github.com/Srikant-03)
