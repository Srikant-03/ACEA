"use client"

import { useState, useEffect } from "react"
import { AgentHexagon } from "@/components/war-room/AgentHexagon"
import { LiveFeed } from "@/components/war-room/LiveFeed"
import { Brain, Code, Shield, Eye, Database, Rocket, Laptop, X } from "lucide-react"
import { socket } from "@/lib/socket"
import { FileExplorer } from "@/components/ide/FileExplorer"
import { CodeEditor } from "@/components/ide/CodeEditor"

export default function WarRoomPage() {
    const [logs, setLogs] = useState<any[]>([])
    const [agents, setAgents] = useState<any>({
        ARCHITECT: "idle",
        VIRTUOSO: "idle",
        SENTINEL: "idle",
        ORACLE: "idle",
        WATCHER: "idle",
        ADVISOR: "idle"
    })
    const [prompt, setPrompt] = useState("")
    const [isProcessing, setIsProcessing] = useState(false)

    // IDE State
    const [projectId, setProjectId] = useState<string | null>(null)
    const [showIDE, setShowIDE] = useState(false)
    const [files, setFiles] = useState<Record<string, string>>({})
    const [selectedFile, setSelectedFile] = useState<string | null>(null)
    const [fileList, setFileList] = useState<string[]>([])

    useEffect(() => {
        // Listen for connection
        socket.on("connect", () => {
            addLog("SYSTEM", "Connected to ACEA Core Uplink", "success")
        })

        // Listen for agent logs
        socket.on("agent_log", (data: any) => {
            addLog(data.agent_name, data.message, "info")
        })

        // Listen for agent status updates
        socket.on("agent_status", (data: any) => {
            setAgents((prev: any) => ({ ...prev, [data.agent_name]: data.status }))
        })

        // Listen for Mission Acceptance (Gets Project ID early)
        socket.on("mission_accepted", (data: { project_id: string }) => {
            setProjectId(data.project_id)
            addLog("SYSTEM", `Mission ID Assigned: ${data.project_id}`, "info")
        })

        // Listen for completion
        socket.on("mission_complete", (data: any) => {
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
            const res = await fetch(`http://localhost:8000/projects/${id}/files`)
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

    const addLog = (agent: string, message: string, type: "info" | "success" | "warning" | "error") => {
        setLogs(prev => [...prev.slice(-49), {
            id: Date.now().toString() + Math.random(),
            agent,
            message,
            timestamp: new Date().toLocaleTimeString(),
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
        socket.emit("start_mission", { prompt })
    }

    return (
        <main className="min-h-screen bg-slate-950 text-white p-6 overflow-hidden relative font-sans">
            {/* Background Grid */}
            <div className="absolute inset-0 bg-[linear-gradient(to_right,#4f4f4f2e_1px,transparent_1px),linear-gradient(to_bottom,#4f4f4f2e_1px,transparent_1px)] bg-[size:14px_24px] pointer-events-none" />

            <div className="relative z-10 grid grid-cols-12 gap-6 h-[calc(100vh-3rem)]">

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

                    <div className="mt-auto">
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
                <div className="col-span-6 flex items-center justify-center relative border border-slate-800/50 rounded-xl bg-slate-950/50 backdrop-blur-sm overflow-hidden">
                    {showIDE && projectId ? (
                        <div className="absolute inset-0 flex flex-row">
                            <FileExplorer
                                files={fileList}
                                onSelect={setSelectedFile}
                                selectedPath={selectedFile || undefined}
                            />
                            <div className="flex-1 bg-[#1e1e1e]">
                                {selectedFile ? (
                                    <CodeEditor
                                        code={files[selectedFile] || ""}
                                        language={selectedFile.endsWith('json') ? 'json' : selectedFile.endsWith('tsx') ? 'typescript' : 'python'}
                                    />
                                ) : (
                                    <div className="h-full flex items-center justify-center text-slate-500">
                                        Select a file to view source
                                    </div>
                                )}
                            </div>
                        </div>
                    ) : (
                        <>
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
                        </>
                    )}
                </div>

                {/* Right Panel: Live Feed */}
                <div className="col-span-3 h-full">
                    <LiveFeed logs={logs} />
                </div>
            </div>
        </main>
    )
}
