# ACEA Architecture

## System Overview

ACEA (Autonomous Codebase Enhancement Agent) uses a **LangGraph state machine** to orchestrate multiple AI agents through a checkpointed, self-healing pipeline.

```
User Prompt → Architect → Virtuoso → Sentinel → Testing → Advisor → Watcher → Browser → Release
                             ↑                                         ↓
                             └──── Self-Healing Loop (max 3 iters) ────┘
```

## Agent Pipeline

| Agent | Module | Role |
|-------|--------|------|
| **Architect** | `agents/architect.py` | Generates system blueprint from user prompt |
| **Virtuoso** | `agents/virtuoso.py` | Generates code files from blueprint; targeted repair on fix iterations |
| **Sentinel** | `agents/sentinel.py` | Security vulnerability scanning (XSS, injection, hardcoded secrets) |
| **Testing** | `agents/testing_agent.py` | Auto-generates and runs tests (pytest/vitest/jest); incremental on fixes |
| **Advisor** | `agents/advisor.py` | Deployment platform recommendation and cost estimation |
| **Watcher** | `agents/watcher.py` | Visual/structural code validation |
| **Browser** | `agents/browser_validator.py` | Playwright-based visual regression testing |
| **Release** | `core/release.py` | Git commit, artifact packaging, deployment |
| **Diagnostician** | `agents/diagnostician.py` | Root-cause analysis for self-healing loop |

## Core Infrastructure

### Orchestrator (`core/orchestrator.py`)
- LangGraph `StateGraph` with conditional edges
- Router decides: loop (errors exist) vs. proceed (clean)
- `_post_process_files()` normalizes LLM output (path dedup, BOM strip, code-fence removal)
- `_validate_file_structure()` catches common generation errors (missing package.json, invalid JSON, missing @tailwindcss/postcss)

### HybridModelClient (`core/HybridModelClient.py`)
- Primary: Gemini API with multi-key rotation
- Fallback: Ollama local models
- Exponential backoff (1s → 30s cap) for transient errors (500, 503, timeouts)
- 120s hard timeout per API call

### SandboxGuard (`core/sandbox_guard.py`)
- Command allowlisting and blocklisting
- Path jailing (restricts file access to project root)
- Rate limiting (max commands/minute)
- Full audit trail

### Checkpoint/Resume (`core/resume_engine.py`)
- Saves full `AgentState` at each node boundary
- Resume from any checkpoint after crash
- Configurable retention policy

### Strategy Engine (`core/strategy_engine.py`)
- Governs self-healing behavior (escalation levels, budget limits)
- Prevents infinite repair loops

### Artifact Generator (`core/artifact_generator.py`)
- Produces `report.json`, `report.md`, `decisions.json`
- Git diff archives
- Emitted via `artifact_report` Socket.IO event from `release_node`

## State Management

```python
class AgentState:
    project_id: str
    blueprint: dict          # Architect output
    file_system: dict        # {path: content}
    errors: list             # Triggers self-healing if non-empty
    issues: list[Issue]      # Security/quality issues
    iteration_count: int     # Current self-healing iteration
    max_iterations: int      # Budget (default: 3)
    changed_files: list      # For incremental test generation
    thought_signatures: list # LLM reasoning traces
    ...
```

## Frontend Architecture

| Component | Path | Purpose |
|-----------|------|---------|
| War Room | `app/war-room/page.tsx` | Main dashboard with live agent feed |
| AgentStage | `components/war-room/AgentStage.tsx` | Animated agent visualization |
| LiveFeed | `components/war-room/LiveFeed.tsx` | Real-time Socket.IO log stream |
| MetricsDashboard | `components/war-room/MetricsDashboard.tsx` | Steps/Latency/Tokens telemetry |
| SystemHealth | `components/war-room/SystemHealth.tsx` | CPU/Memory/Neural Load bars |
| NetworkMap | `components/war-room/NetworkMap.tsx` | Animated uplink status globe |
| TimeTravel | `components/war-room/TimeTravel.tsx` | State snapshot navigation |
| FileExplorer | `components/explorer/FileExplorer.tsx` | Project file tree browser |
| CodeEditor | `components/ide/CodeEditor.tsx` | Monaco-based code editor |
| PreviewPanel | `components/preview/PreviewPanel.tsx` | Live app preview iframe |

## Communication

- **Socket.IO** for real-time events: `agent_log`, `agent_status`, `file_generated`, `state_update`, `metrics`, `artifact_report`
- **REST API** for CRUD: file management, project execution, documentation generation
- **E2B Sandbox** for cloud-based project execution with VS Code integration
