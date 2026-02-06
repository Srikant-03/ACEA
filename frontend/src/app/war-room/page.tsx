"use client"

import { useState, useEffect } from "react"
import { AgentHexagon } from "@/components/war-room/AgentHexagon"
import { LiveFeed } from "@/components/war-room/LiveFeed"
import { Brain, Code, Shield, Eye, Database, Rocket, Laptop, X, Play, Square, Bug, Download, FileText, Wand2 } from "lucide-react"
import { socket } from "@/lib/socket"
import { FileExplorer } from "@/components/ide/FileExplorer"
import { CodeEditor } from "@/components/ide/CodeEditor"
import { PreviewPanel } from "@/components/preview/PreviewPanel"
import type {
    AgentLog,
    AgentStatusUpdate,
    MissionAccepted,
    MissionComplete,
    MissionError,
    GenerationStarted,
    FileGenerated,
    LogEntry,
    AgentsState,
    LogLevel
} from "@/types/socket"

export default function WarRoomPage() {
    const [logs, setLogs] = useState<LogEntry[]>([])
    const [agents, setAgents] = useState<AgentsState>({
        ARCHITECT: "idle",
        VIRTUOSO: "idle",
        SENTINEL: "idle",
        ORACLE: "idle",
        WATCHER: "idle",
        ADVISOR: "idle",
        SYSTEM: "idle"
    })
    const [prompt, setPrompt] = useState("")
    const [techStack, setTechStack] = useState("Auto-detect")
    const [isProcessing, setIsProcessing] = useState(false)

    // IDE State
    const [projectId, setProjectId] = useState<string | null>(null)
    const [showIDE, setShowIDE] = useState(false)
    const [files, setFiles] = useState<Record<string, string>>({})
    const [selectedFile, setSelectedFile] = useState<string | null>(null)
    const [fileList, setFileList] = useState<string[]>([])

    // Execution State (E2B only)
    const [executionStatus, setExecutionStatus] = useState<'idle' | 'running' | 'stopped' | 'error'>('idle')
    const [executionLogs, setExecutionLogs] = useState<string>('')
    const [showPreview, setShowPreview] = useState(false)
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)
    const [previewTechStack, setPreviewTechStack] = useState<string>('')
    const [isLoadingPreview, setIsLoadingPreview] = useState(false)
    const [loadingStage, setLoadingStage] = useState<string>('Creating sandbox...')

    useEffect(() => {
        // Listen for connection
        socket.on("connect", () => {
            addLog("SYSTEM", "Connected to ACEA Core Uplink", "success")
        })

        // Listen for agent logs
        socket.on("agent_log", (data: AgentLog) => {
            addLog(data.agent_name, data.message, "info")
        })

        // Listen for agent status updates
        socket.on("agent_status", (data: AgentStatusUpdate) => {
            setAgents((prev: AgentsState) => ({ ...prev, [data.agent_name]: data.status }))
        })

        // Listen for Mission Acceptance (Gets Project ID early)
        socket.on("mission_accepted", (data: { project_id: string }) => {
            setProjectId(data.project_id)
            addLog("SYSTEM", `Mission ID Assigned: ${data.project_id}`, "info")
        })

        // Listen for completion
        socket.on("mission_complete", (data: MissionComplete) => {
            setIsProcessing(false)
            addLog("SYSTEM", "Mission Objective Complete", "success")

            if (data.project_id) {
                setProjectId(data.project_id)
                fetchProjectFiles(data.project_id)
                setShowIDE(true) // Auto-open IDE
            }
        })

        // Listen for errors
        socket.on("mission_error", (data) => {
            setIsProcessing(false)
            addLog("SYSTEM", `Critical Failure: ${data.detail}`, "error")
        })

        // Listen for Real-Time Generation Events
        socket.on("generation_started", (data: { total_files: number, file_list: string[] }) => {
            addLog("VIRTUOSO", `Planned ${data.total_files} files. Starting stream...`, "info")
            // Initialize file list with pending status if we wanted, or just wait
            setFileList(data.file_list)
            setShowIDE(true) // Auto-open IDE immediately
        })

        socket.on("file_generated", (data: { path: string, content: string, status: string }) => {
            // Update files state incrementally
            setFiles(prev => ({
                ...prev,
                [data.path]: data.content
            }))
            // Also select it if it's the first one or we want to follow the cursor (optional)
            // setSelectedFile(data.path) 
            addLog("VIRTUOSO", `Generated: ${data.path}`, "success")
        })

        socket.on("file_status", (data: { path: string, status: string }) => {
            if (data.status === 'generating') {
                addLog("VIRTUOSO", `Developing: ${data.path}...`, "info")
            }
        })

        return () => {
            socket.off("connect")
            socket.off("agent_log")
            socket.off("agent_status")
            socket.off("mission_complete")
            socket.off("mission_error")
        }
    }, [])

    const fetchProjectFiles = async (id: string) => {
        try {
            const res = await fetch(`http://localhost:8000/api/projects/${id}/files`)
            const data = await res.json()
            // data is dict {path: content} from backend
            setFiles(data)
            const paths = Object.keys(data).sort()
            setFileList(paths)
            if (paths.length > 0) setSelectedFile(paths[0])
        } catch (e) {
            console.error("Failed to fetch files", e)
        }
    }

    const addLog = (agent: string, message: string, type: LogLevel) => {
        setLogs(prev => [...prev.slice(-49), {
            id: Date.now().toString() + Math.random(),
            agent,
            message,
            timestamp: new Date(),
            type
        }])
    }

    const startMission = () => {
        if (!prompt.trim()) return
        setIsProcessing(true)
        setLogs([]) // Clear previous logs
        setShowIDE(false) // Reset view
        addLog("SYSTEM", "Initializing Autonomous Sequence...", "warning")

        // Emit start event to backend
        socket.emit("start_mission", { prompt, tech_stack: techStack })
    }

    // ============ EXECUTION HANDLERS ============
    const handleExecute = async () => {
        if (!projectId) return
        setExecutionStatus('running')
        setIsLoadingPreview(true)
        setLoadingStage('Creating sandbox (this takes 2-3 seconds)...')
        setShowPreview(true)
        addLog('SYSTEM', '🚀 Creating E2B cloud sandbox...', 'info')

        try {
            const res = await fetch(`http://localhost:8000/api/execute/${projectId}`, { method: 'POST' })
            const data = await res.json()

            setIsLoadingPreview(false)

            if (data.status === 'error') {
                setExecutionStatus('error')
                setShowPreview(false)
                addLog('SYSTEM', data.message || 'Execution failed', 'error')
                if (data.logs) {
                    setExecutionLogs(data.logs)
                }
                return
            }

            // E2B response: { status, logs, preview_url, sandbox_id, message, stage }
            if (data.preview_url) {
                setPreviewUrl(data.preview_url)
                setPreviewTechStack(data.message?.match(/\(([^)]+)\)/)?.[1] || '')
                setExecutionStatus('running')
                setExecutionLogs(data.logs || '')
                addLog('SYSTEM', `✅ ${data.message}`, 'success')
                addLog('SYSTEM', `🌐 Preview: ${data.preview_url}`, 'info')
            } else {
                setExecutionStatus('error')
                setShowPreview(false)
                addLog('SYSTEM', 'No preview URL received', 'error')
            }
        } catch (e) {
            setExecutionStatus('error')
            setIsLoadingPreview(false)
            setShowPreview(false)
            addLog('SYSTEM', 'Failed to connect to execution service', 'error')
        }
    }

    const pollLogs = async () => {
        if (!projectId) return
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`http://localhost:8000/api/logs/${projectId}`)
                const data = await res.json()
                setExecutionLogs(data.logs || '')
            } catch (e) {
                clearInterval(interval)
            }
        }, 3000)
        // Store interval for cleanup (simplified - just run 10 times)
        setTimeout(() => clearInterval(interval), 30000)
    }

    const handleStop = async () => {
        if (!projectId) return
        try {
            await fetch(`http://localhost:8000/api/stop/${projectId}`, { method: 'POST' })
            setExecutionStatus('stopped')
            setShowPreview(false)
            setPreviewUrl(null)
            addLog('SYSTEM', '⏹️ Sandbox stopped', 'warning')
        } catch (e) {
            addLog('SYSTEM', 'Failed to stop execution', 'error')
        }
    }

    const handleDebug = async () => {
        if (!projectId) return
        addLog('TESTER', 'Analyzing execution logs...', 'info')
        try {
            const res = await fetch(`http://localhost:8000/api/debug/${projectId}`, { method: 'POST' })
            const data = await res.json()
            if (data.issues_found?.length > 0) {
                data.issues_found.forEach((issue: string) => addLog('TESTER', `Issue: ${issue}`, 'warning'))
                data.suggestions?.forEach((s: string) => addLog('TESTER', `Suggestion: ${s}`, 'info'))
            } else {
                addLog('TESTER', 'No issues detected in logs', 'success')
            }
        } catch (e) {
            addLog('SYSTEM', 'Debug analysis failed', 'error')
        }
    }

    const handleDownload = async () => {
        if (!projectId) return
        window.open(`http://localhost:8000/api/projects/${projectId}/download`, '_blank')
        addLog('SYSTEM', 'Download started', 'success')
    }

    const handleGenerateDocs = async () => {
        if (!projectId) return
        addLog('DOCUMENTER', 'Generating README.md...', 'info')
        try {
            const res = await fetch(`http://localhost:8000/api/generate-docs/${projectId}`, { method: 'POST' })
            const data = await res.json()
            if (data.status === 'generated') {
                addLog('DOCUMENTER', 'README.md generated successfully', 'success')
                fetchProjectFiles(projectId) // Refresh file list
            }
        } catch (e) {
            addLog('SYSTEM', 'Documentation generation failed', 'error')
        }
    }

    const handleAIEdit = async () => {
        if (!projectId || !selectedFile) return
        const instruction = window.prompt('What would you like to change in this file?')
        if (!instruction) return

        addLog('SYSTEM', 'AI editing file...', 'info')
        try {
            const res = await fetch(`http://localhost:8000/api/update-file-ai/${projectId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_path: selectedFile,
                    instruction: instruction
                })
            })
            const data = await res.json()
            if (data.status === 'success') {
                setFiles(prev => ({ ...prev, [selectedFile]: data.updated_content }))
                addLog('SYSTEM', `File updated: ${selectedFile}`, 'success')
            }
        } catch (e) {
            addLog('SYSTEM', 'AI edit failed', 'error')
        }
    }

    return (
        <main className="min-h-screen bg-slate-950 text-white p-6 overflow-y-auto relative font-sans">
            {/* Background Grid */}
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#4f4f4f2e_1px,transparent_1px),linear-gradient(to_bottom,#4f4f4f2e_1px,transparent_1px)] bg-[size:14px_24px] pointer-events-none" />

            <div className="relative z-10 grid grid-cols-12 gap-6 min-h-[calc(100vh-3rem)]">

                {/* Left Panel: Metrics & Input */}
                <div className="col-span-3 border border-slate-800 bg-slate-950/80 p-4 rounded-xl backdrop-blur-md flex flex-col">
                    <h2 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent mb-6">MISSION CONTROL</h2>

                    <div className="space-y-4 mb-4">
                        <div className="p-3 bg-slate-900/50 border border-slate-800 rounded flex justify-between items-center">
                            <div className="text-slate-500 text-xs uppercase">Security Level</div>
                            <div className="text-green-400 font-mono font-bold">DEFCON 5</div>
                        </div>
                        {projectId && (
                            <button
                                onClick={() => setShowIDE(!showIDE)}
                                className={`w-full py-2 rounded font-bold text-sm flex items-center justify-center gap-2 transition-colors ${showIDE ? 'bg-slate-800 text-white' : 'bg-purple-600 hover:bg-purple-500 text-white'}`}
                            >
                                {showIDE ? <X className="w-4 h-4" /> : <Laptop className="w-4 h-4" />}
                                {showIDE ? "CLOSE IDE" : "OPEN CODEBASE"}
                            </button>
                        )}
                    </div>

                    {/* Execution Controls */}
                    {projectId && (
                        <div className="mb-4 space-y-2">
                            <div className="text-xs text-slate-400 uppercase font-bold mb-2">Execution Controls</div>
                            <div className="flex gap-2">
                                <button
                                    onClick={handleExecute}
                                    disabled={executionStatus === 'running'}
                                    className="flex-1 bg-green-600 hover:bg-green-500 disabled:bg-slate-700 text-white py-2 rounded text-xs font-bold flex items-center justify-center gap-1"
                                >
                                    <Play className="w-3 h-3" /> RUN
                                </button>
                                <button
                                    onClick={handleStop}
                                    disabled={executionStatus !== 'running'}
                                    className="flex-1 bg-red-600 hover:bg-red-500 disabled:bg-slate-700 text-white py-2 rounded text-xs font-bold flex items-center justify-center gap-1"
                                >
                                    <Square className="w-3 h-3" /> STOP
                                </button>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={handleDebug}
                                    className="flex-1 bg-yellow-600 hover:bg-yellow-500 text-white py-2 rounded text-xs font-bold flex items-center justify-center gap-1"
                                >
                                    <Bug className="w-3 h-3" /> DEBUG
                                </button>
                                <button
                                    onClick={handleGenerateDocs}
                                    className="flex-1 bg-purple-600 hover:bg-purple-500 text-white py-2 rounded text-xs font-bold flex items-center justify-center gap-1"
                                >
                                    <FileText className="w-3 h-3" /> DOCS
                                </button>
                            </div>
                            <button
                                onClick={handleDownload}
                                className="w-full bg-blue-600 hover:bg-blue-500 text-white py-2 rounded text-xs font-bold flex items-center justify-center gap-1"
                            >
                                <Download className="w-3 h-3" /> DOWNLOAD ZIP
                            </button>
                            {executionStatus !== 'idle' && (
                                <div className={`text-xs text-center py-1 rounded ${executionStatus === 'running' ? 'bg-green-900/30 text-green-400' : executionStatus === 'error' ? 'bg-red-900/30 text-red-400' : 'bg-slate-800 text-slate-400'}`}>
                                    Status: {executionStatus.toUpperCase()}
                                </div>
                            )}
                        </div>
                    )}

                    <div className="mt-auto">
                        <label className="text-xs text-slate-400 uppercase font-bold mb-2 block">Tech Stack Protocol</label>
                        <select
                            value={techStack}
                            onChange={(e) => setTechStack(e.target.value)}
                            className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-sm text-white focus:outline-none focus:border-blue-500 mb-4"
                        >
                            <option value="Auto-detect">Auto-detect (Recommended)</option>
                            <option value="Next.js + FastAPI">Next.js + FastAPI</option>
                            <option value="React + Node.js">React + Node.js</option>
                            <option value="Vue + Python">Vue + Python</option>
                            <option value="Vanilla HTML/JS">Vanilla HTML/JS</option>
                            <option value="Python Script">Python Script</option>
                        </select>

                        <label className="text-xs text-slate-400 uppercase font-bold mb-2 block">Mission Objective</label>
                        <textarea
                            className="w-full bg-slate-900 border border-slate-700 rounded p-3 text-sm text-white focus:outline-none focus:border-blue-500 h-32 mb-4 resize-none"
                            placeholder="Describe the software you want to build..."
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            disabled={isProcessing}
                        />
                        {/* Status bar */}
                        {isProcessing && (
                            <div className="text-xs text-blue-400 animate-pulse mb-2 text-center">
                                Processing Mission Data...
                            </div>
                        )}
                        <button
                            onClick={startMission}
                            disabled={isProcessing || !prompt}
                            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 text-white font-bold py-3 rounded shadow-lg transition-all flex items-center justify-center gap-2"
                        >
                            {isProcessing ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Rocket className="w-4 h-4" />}
                            {isProcessing ? "EXECUTING..." : "INITIATE LAUNCH"}
                        </button>
                    </div>
                </div>

                {/* Center Panel: Visualization OR IDE */}
                <div className="col-span-6 relative border border-slate-800/50 rounded-xl bg-slate-950/50 backdrop-blur-sm overflow-hidden flex flex-col">
                    {showIDE && projectId ? (
                        <div className="absolute inset-0 flex flex-col">
                            {/* Editor + Sidebar Area */}
                            <div className="flex-1 flex flex-row overflow-hidden">
                                <FileExplorer
                                    files={fileList}
                                    onSelect={setSelectedFile}
                                    selectedPath={selectedFile || undefined}
                                />
                                <div className="flex-1 bg-[#1e1e1e] flex flex-col overflow-hidden">
                                    {selectedFile ? (
                                        <>
                                            <div className="flex items-center justify-between bg-[#252526] px-3 py-1.5 border-b border-slate-700">
                                                <span className="text-xs text-slate-400 font-mono">{selectedFile}</span>
                                                <button
                                                    onClick={handleAIEdit}
                                                    className="flex items-center gap-1 bg-violet-600 hover:bg-violet-500 text-white text-xs px-2 py-1 rounded"
                                                >
                                                    <Wand2 className="w-3 h-3" /> AI Edit
                                                </button>
                                            </div>
                                            <div className="flex-1 overflow-hidden">
                                                <CodeEditor
                                                    code={files[selectedFile] || ""}
                                                    language={selectedFile.endsWith('json') ? 'json' : selectedFile.endsWith('tsx') ? 'typescript' : 'python'}
                                                />
                                            </div>
                                        </>
                                    ) : (
                                        <div className="h-full flex items-center justify-center text-slate-500">
                                            Select a file to view source
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Execution Logs Panel - Always visible in IDE mode if logs exist */}
                            {executionLogs && (
                                <div className="w-full h-48 bg-black/90 border-t border-slate-700 p-2 overflow-auto font-mono text-xs text-green-400">
                                    <div className="text-slate-500 mb-1 flex justify-between items-center">
                                        <span>--- Execution Logs ---</span>
                                        <button onClick={() => setExecutionLogs('')} className="hover:text-white">Clear</button>
                                    </div>
                                    <pre className="whitespace-pre-wrap">{executionLogs}</pre>
                                </div>
                            )}

                            {/* Preview Panel - Overlays the IDE when active */}
                            {showPreview && (previewUrl || isLoadingPreview) && (
                                <div className="absolute inset-0 z-20">
                                    <PreviewPanel
                                        previewUrl={previewUrl || undefined}
                                        techStack={previewTechStack}
                                        isLoading={isLoadingPreview}
                                        loadingStage={loadingStage}
                                        onClose={() => {
                                            setShowPreview(false)
                                            if (previewUrl && executionStatus === 'running') {
                                                handleStop()
                                            }
                                        }}
                                    />
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="h-full w-full flex items-center justify-center relative">
                            <div className="grid grid-cols-3 gap-8 place-items-center relative z-10">
                                <AgentHexagon name="ARCHITECT" status={agents.ARCHITECT} icon={Brain} />
                                <AgentHexagon name="VIRTUOSO" status={agents.VIRTUOSO} icon={Code} className="mt-12" />
                                <AgentHexagon name="SENTINEL" status={agents.SENTINEL} icon={Shield} />

                                <AgentHexagon name="ORACLE" status={agents.ORACLE} icon={Database} />
                                <AgentHexagon name="WATCHER" status={agents.WATCHER} icon={Eye} className="mt-12" />
                                <AgentHexagon name="ADVISOR" status={agents.ADVISOR} icon={Rocket} />
                            </div>
                            <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-20">
                                <circle cx="50%" cy="50%" r="200" fill="none" stroke="currentColor" className="text-blue-500 animate-spin-slow" strokeDasharray="10 10" />
                            </svg>
                        </div>
                    )}
                </div>

                {/* Right Panel: Live Feed */}
                <div className="col-span-3 h-full">
                    <LiveFeed logs={logs} />
                </div>
            </div>
        </main >
    )
}
