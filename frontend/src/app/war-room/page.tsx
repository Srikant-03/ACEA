"use client"

import { useState, useEffect } from "react"
import { AgentStage } from "@/components/war-room/AgentStage"
import { LiveFeed } from "@/components/war-room/LiveFeed"
import { SystemLaneWalker } from "@/components/war-room/SystemLaneWalker"
import {
    Brain, Code, Shield, Eye, Database, Rocket, Laptop, X,
    Play, Square, Bug, Download, FileText, Wand2, Zap, Radio, Layout, Podcast
} from "lucide-react"
import { socket } from "@/lib/socket"
import { FileExplorer } from "@/components/ide/FileExplorer"
import { CodeEditor } from "@/components/ide/CodeEditor"
import { PreviewPanel } from "@/components/preview/PreviewPanel"
import { cn } from "@/lib/utils"
import { motion } from "framer-motion"
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
    // --- CORE LOGIC STATE (Untouched) ---
    const [logs, setLogs] = useState<any[]>([])
    const [agents, setAgents] = useState<any>({
        ARCHITECT: "idle", VIRTUOSO: "idle", SENTINEL: "idle",
        ORACLE: "idle", WATCHER: "idle", ADVISOR: "idle"
    })
    const [prompt, setPrompt] = useState("")
    const [techStack, setTechStack] = useState("Auto-detect")
    const [isProcessing, setIsProcessing] = useState(false)
    const [projectId, setProjectId] = useState<string | null>(null)
    const [files, setFiles] = useState<Record<string, string>>({})
    const [selectedFile, setSelectedFile] = useState<string | null>(null)
    const [fileList, setFileList] = useState<string[]>([])

    // Execution State (E2B only)
    const [executionStatus, setExecutionStatus] = useState<'idle' | 'running' | 'stopped' | 'error'>('idle')
    const [executionLogs, setExecutionLogs] = useState<string>('')
    const [showPreview, setShowPreview] = useState(false)
    const [previewUrl, setPreviewUrl] = useState<string | null>(null)
    const [vscodeUrl, setVscodeUrl] = useState<string | null>(null)
    const [sandboxId, setSandboxId] = useState<string | null>(null)
    const [previewTechStack, setPreviewTechStack] = useState<string>('')
    const [isLoadingPreview, setIsLoadingPreview] = useState(false)
    const [loadingStage, setLoadingStage] = useState<string>('Creating sandbox...')

    // --- REFINED UI STATE ---
    const [activeTab, setActiveTab] = useState<'codebase' | 'preview'>('codebase')
    const [showLiveFeed, setShowLiveFeed] = useState(true)
    const [showIDE, setShowIDE] = useState(false)
    const [mounted, setMounted] = useState(false)

    // VS Code Full-Screen State
    const [showFullScreenVSCode, setShowFullScreenVSCode] = useState(false)
    const [showWelcomeBanner, setShowWelcomeBanner] = useState(false)
    const [projectType, setProjectType] = useState<string>('')
    const [vsCodePort, setVsCodePort] = useState<number>(3000)

    useEffect(() => {
        setMounted(true)
    }, [])

    // Agent icons for the "Cute" floating animation
    const agentIcons = [
        { Icon: Brain, color: "text-zinc-600" },
        { Icon: Code, color: "text-zinc-500" },
        { Icon: Shield, color: "text-zinc-700" },
        { Icon: Database, color: "text-zinc-400" },
        { Icon: Eye, color: "text-zinc-600" },
        { Icon: Rocket, color: "text-zinc-500" }
    ]

    const getLanguage = (filename: string) => {
        const ext = filename.split('.').pop()?.toLowerCase()
        if (ext === 'html') return 'html'
        if (ext === 'css') return 'css'
        if (ext === 'tsx' || ext === 'ts') return 'typescript'
        return 'javascript'
    }

    // ... (socket UseEffect logic remains same)

    useEffect(() => {
        socket.on("connect", () => addLog("SYSTEM", "Connected to ACEA Core Uplink", "success"))
        socket.on("agent_log", (data: any) => addLog(data.agent_name, data.message, "info"))
        socket.on("agent_status", (data: any) => setAgents((prev: any) => ({ ...prev, [data.agent_name]: data.status })))
        socket.on("mission_accepted", (data: { project_id: string }) => setProjectId(data.project_id))
        socket.on("mission_complete", (data: any) => {
            setIsProcessing(false)
            if (data.project_id) {
                setProjectId(data.project_id)
                fetchProjectFiles(data.project_id)
                setShowIDE(true)
            }
        })
        socket.on("generation_started", (data: { file_list: string[] }) => {
            setFileList(data.file_list); setShowIDE(true)
        })
        socket.on("file_generated", (data: { path: string, content: string }) => {
            setFiles(prev => ({ ...prev, [data.path]: data.content }))
        })

        // VS Code ready event - auto-opens full-screen VS Code
        socket.on("vscode_ready", (data: any) => {
            setVscodeUrl(data.vscode_url)
            setPreviewUrl(data.preview_url)
            setSandboxId(data.sandbox_id)
            setProjectType(data.project_type || 'unknown')
            setVsCodePort(data.port || 3000)
            setShowFullScreenVSCode(true)
            setShowWelcomeBanner(true)
            setExecutionStatus('running')
            setIsLoadingPreview(false)
            addLog('SYSTEM', `✅ VS Code ready! Preview: ${data.preview_url}`, 'success')
        })

        socket.on("vscode_error", (data: any) => {
            addLog('SYSTEM', `⚠️ VS Code setup failed: ${data.error}`, 'error')
            setIsLoadingPreview(false)
        })

        return () => {
            socket.off("connect")
            socket.off("agent_log")
            socket.off("agent_status")
            socket.off("mission_accepted")
            socket.off("mission_complete")
            socket.off("generation_started")
            socket.off("file_generated")
            socket.off("vscode_ready")
            socket.off("vscode_error")
        }
    }, [])

    const fetchProjectFiles = async (id: string) => {
        try {
            const res = await fetch(`http://localhost:8000/api/projects/${id}/files`)
            const data = await res.json()
            setFiles(data); setFileList(Object.keys(data).sort())
            if (Object.keys(data).length > 0) setSelectedFile(Object.keys(data).sort()[0])
        } catch (e) { console.error(e) }
    }

    const addLog = (agent: string, message: string, type: string) => {
        // Use a more unique ID generation for safety
        const uniqueId = `${Date.now()}-${Math.random()}`;
        setLogs(prev => [...prev.slice(-49), { id: uniqueId, agent, message, timestamp: new Date().toLocaleTimeString(), type }])
    }

    const startMission = () => {
        if (!prompt.trim()) return
        setIsProcessing(true); setLogs([]); setShowIDE(false)
        socket.emit("start_mission", { prompt, tech_stack: techStack })
    }

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

            // E2B response: { status, logs, preview_url, vscode_url, sandbox_id, message, stage }
            if (data.vscode_url) {
                setVscodeUrl(data.vscode_url)
                setSandboxId(data.sandbox_id || null)
                addLog('SYSTEM', `🖥️ VS Code: ${data.vscode_url}`, 'info')
            }

            if (data.embed_url || data.preview_url) {
                setPreviewUrl(data.embed_url || data.preview_url)
                setPreviewTechStack(data.message?.match(/\(([^)]+)\)/)?.[1] || '')
                setExecutionStatus('running')
                setExecutionLogs(data.logs || '')
                setActiveTab('codebase') // Show VS Code in codebase tab
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
            // Try VS Code stop first, then fallback to regular stop
            try {
                await fetch(`http://localhost:8000/api/vscode/stop/${projectId}`, { method: 'POST' })
            } catch {
                await fetch(`http://localhost:8000/api/stop/${projectId}`, { method: 'POST' })
            }
            setExecutionStatus('stopped')
            setShowPreview(false)
            setShowFullScreenVSCode(false)
            setShowWelcomeBanner(false)
            setPreviewUrl(null)
            setVscodeUrl(null)
            setSandboxId(null)
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
        <>
            <main className="min-h-screen bg-[#09090b] text-zinc-200 p-6 overflow-hidden relative font-sans selection:bg-white/20">
                {/* Cinematic Background: Pure Zinc - No External Noise (Potential Blue Tint) */}
                <div className="absolute inset-0 bg-[#09090b] pointer-events-none" />

                {/* Internal Grain Simulation using CSS radial gradient noise if needed, but keeping it clean for now */}
                <div className="absolute inset-0 opacity-[0.02] pointer-events-none bg-[radial-gradient(circle_at_center,#ffffff_1px,transparent_1px)] [background-size:24px_24px]" />

                <div className="relative z-10 flex gap-6 h-[calc(100vh-3rem)] w-full">


                    {/* Left Panel: Mission Control */}
                    <div className="w-[22%] min-w-[280px] bg-white/5 backdrop-blur-xl border border-white/5 p-6 rounded-3xl flex flex-col shadow-2xl shrink-0">
                        <h2 className="text-xl font-orbitron font-bold tracking-widest text-white/90 mb-8 uppercase drop-shadow-[0_0_10px_rgba(255,255,255,0.3)]">Mission Control</h2>

                        {projectId && (
                            <button onClick={() => setShowIDE(!showIDE)} className="w-full py-3 mb-8 rounded-xl font-orbitron text-[10px] font-bold tracking-[0.2em] flex items-center justify-center gap-2 border border-blue-900/30 bg-blue-950/40 text-blue-400 hover:bg-blue-900/60 hover:border-blue-700/50 hover:shadow-[0_0_20px_rgba(59,130,246,0.2)] transition-all uppercase">
                                {showIDE ? <X className="w-4 h-4" /> : <Laptop className="w-4 h-4" />}
                                {showIDE ? "DISCONNECT CORE" : "ACCESS CODEBASE"}
                            </button>
                        )}

                        {/* TACTICAL EXECUTION BUTTONS: Consistent Width, Hover Reveal */}


                        {/* AGENT ANIMATION AREA */}
                        {/* INPUT AREA: Dual-Purpose Component */}
                        <div className="space-y-4">
                            <select value={techStack} onChange={(e) => setTechStack(e.target.value)} className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-[10px] font-orbitron font-bold uppercase tracking-widest text-slate-400 outline-none hover:border-white/20 transition-colors focus:border-cyan-500/50">
                                <option value="Auto-detect">AUTO-DETECT PROTOCOL</option>
                            </select>

                            {/* Mission Objective Input + Animation Lane */}
                            <div className="relative w-full h-48 bg-black border border-white/10 rounded-xl overflow-hidden group hover:border-white/20 transition-colors focus-within:border-cyan-500/50 shadow-[inset_0_2px_10px_rgba(0,0,0,0.5)] flex flex-col">
                                {/* Scrollable Input Area */}
                                <div className="flex-1 overflow-y-auto custom-scrollbar relative z-10">
                                    <textarea
                                        className="w-full h-full bg-transparent border-none p-4 text-[12px] text-cyan-100/90 resize-none outline-none font-mono placeholder:text-slate-600 block"
                                        value={prompt}
                                        onChange={(e) => setPrompt(e.target.value)}
                                        disabled={isProcessing}
                                        placeholder="ENTER MISSION OBJECTIVES..."
                                    />
                                </div>

                                {/* Fixed System Execution Lane (Footer) */}
                                {/* REPLACE VIDEOS HERE: Update the 'video' path in the entities array below */}
                                <div className="relative shrink-0 h-16 w-full bg-black border-t border-white/5 z-0">
                                    <SystemLaneWalker
                                        className="h-16 w-full"
                                        entities={[
                                            { video: "/videos/robot.mp4", name: "Virtuoso", intro: "Execute flawlessly" },
                                            { video: "/videos/shiel.mp4", name: "Sentinel", intro: "Scan threats" },
                                            { video: "/videos/Settings.mp4", name: "Oracle", intro: "Predict outcomes" },
                                            { video: "/videos/Brain.mp4", name: "Architect", intro: "Design systems" },
                                            { video: "/videos/Eyes.mp4", name: "Warden", intro: "Lock down" },
                                            { video: "/videos/Earth.mp4", name: "Advisor", intro: "Guide decisions" }
                                        ]}
                                    />
                                </div>
                            </div>

                            {/* Initiate Launch Button */}
                            <button onClick={startMission} disabled={isProcessing || !prompt} className="w-full bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 text-zinc-200 font-orbitron font-bold py-4 rounded-xl flex items-center justify-center gap-3 uppercase text-[10px] tracking-[0.3em] shadow-[0_0_20px_rgba(255,255,255,0.05)] hover:shadow-[0_0_30px_rgba(255,255,255,0.1)] transition-all">
                                {isProcessing ? <Zap className="w-4 h-4 animate-pulse text-white" /> : "INITIATE LAUNCH"}
                            </button>

                            {/* Tactical Execution - Compact Toolbar */}
                            <div className="flex gap-2">
                                {[
                                    { icon: Play, label: 'RUN SYSTEM', onClick: handleExecute, color: 'text-emerald-300 hover:text-emerald-200' },
                                    { icon: Square, label: 'STOP SYSTEM', onClick: handleStop, color: 'text-rose-300 hover:text-rose-200' },
                                    { icon: Bug, label: 'DEBUG MODULE', onClick: handleDebug, color: 'text-amber-300 hover:text-amber-200' },
                                    { icon: FileText, label: 'DOCS MANIFEST', onClick: () => { }, color: 'text-violet-300 hover:text-violet-200' },
                                    { icon: Download, label: 'EXPORT ZIP', onClick: handleDownload, color: 'text-sky-300 hover:text-sky-200' }
                                ].map((btn, i) => (
                                    <div key={i} className="relative group flex-1">
                                        <button
                                            onClick={btn.onClick}
                                            className={cn(
                                                "flex items-center justify-center h-10 w-full rounded-lg border border-white/5 bg-white/5 hover:bg-white/10 transition-all shadow-md active:scale-95",
                                                btn.color
                                            )}
                                        >
                                            <btn.icon className="w-4 h-4" />
                                        </button>
                                        {/* Tooltip */}
                                        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 bg-zinc-900 border border-white/10 text-zinc-300 text-[9px] font-bold px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50 uppercase tracking-widest shadow-xl">
                                            {btn.label}
                                            {/* Arrow */}
                                            <div className="absolute top-full left-1/2 -translate-x-1/2 w-2 h-2 bg-zinc-900 border-r border-b border-white/10 rotate-45 -mt-1" />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Center Panel: Maximum Horizontal Length Housing */}
                    <div className="flex-1 flex flex-col relative min-w-0">

                        {/* Navigation Row: Fixed Header to prevent Overlap */}
                        {showIDE && (
                            <div className="flex items-center justify-between mb-4 px-2 bg-zinc-950/80 backdrop-blur-md py-2 border-b border-white/5 z-50">
                                {/* Switched Pill - Sleek Charcoal */}
                                <div className="flex items-center bg-black/40 border border-white/5 p-1 rounded-xl flex-1 max-w-xl mx-auto backdrop-blur-sm">
                                    <button
                                        onClick={() => setActiveTab('codebase')}
                                        className={cn(
                                            "flex-1 flex items-center justify-center gap-2 py-2 rounded-lg font-orbitron font-bold text-[12px] tracking-widest uppercase transition-all duration-300 relative overflow-hidden",
                                            activeTab === 'codebase'
                                                ? "text-zinc-100 shadow-[0_0_15px_rgba(255,255,255,0.05)] bg-white/5 border border-white/10"
                                                : "text-zinc-600 hover:text-zinc-400 hover:bg-white/5"
                                        )}
                                    >
                                        <Layout className="w-3 h-3" /> CODEBASE
                                    </button>
                                    <button
                                        onClick={() => setActiveTab('preview')}
                                        className={cn(
                                            "flex-1 flex items-center justify-center gap-2 py-2 rounded-lg font-orbitron font-bold text-[12px] tracking-widest uppercase transition-all duration-300 relative overflow-hidden",
                                            activeTab === 'preview'
                                                ? "text-zinc-100 shadow-[0_0_15px_rgba(255,255,255,0.05)] bg-white/5 border border-white/10"
                                                : "text-zinc-600 hover:text-zinc-400 hover:bg-white/5"
                                        )}
                                    >
                                        <Eye className="w-3 h-3" /> PREVIEW
                                    </button>
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

                                {/* Live Feed Toggle: Subtle */}
                                <button
                                    onClick={() => setShowLiveFeed(!showLiveFeed)}
                                    className={cn(
                                        "p-2 rounded-lg border transition-all duration-300 ml-4 absolute top-2 right-2 z-10",
                                        showLiveFeed
                                            ? "bg-white/5 border-white/10 text-zinc-300 shadow-[0_0_10px_rgba(255,255,255,0.05)]"
                                            : "bg-transparent border-transparent text-zinc-700 hover:text-zinc-400"
                                    )}
                                >
                                    <Podcast className="w-4 h-4" />
                                </button>
                            </div>
                        )}

                        {/* MAIN CONTENT AREA */}
                        <div className="flex-1 relative overflow-hidden flex bg-[#09090b] rounded-2xl border border-white/5 shadow-2xl">
                            {showIDE ? (
                                activeTab === 'codebase' ? (
                                    vscodeUrl ? (
                                        /* VS Code iframe when sandbox is running */
                                        <div className="h-full w-full relative">
                                            <iframe
                                                src={vscodeUrl}
                                                className="h-full w-full border-none"
                                                title="VS Code"
                                                allow="clipboard-read; clipboard-write"
                                            />
                                            {/* Sandbox status indicator */}
                                            <div className="absolute top-2 right-2 flex items-center gap-2 bg-black/80 backdrop-blur-sm px-3 py-1.5 rounded-full border border-emerald-500/30">
                                                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                                                <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">Sandbox Active</span>
                                            </div>
                                        </div>
                                    ) : (
                                        /* Fallback: Explorer + Built-in Editor when no sandbox */
                                        <div className="h-full w-full flex">
                                            {/* EXPLORER - Charcoal Aesthetic */}
                                            <div className="w-64 shrink-0 border-r border-white/10 bg-zinc-900/40 backdrop-blur-md flex flex-col">
                                                <div className="p-3 border-b border-white/5">
                                                    <span className="text-[10px] font-bold text-zinc-500 tracking-[0.2em] uppercase">Explorer</span>
                                                </div>
                                                <div className="flex-1 overflow-y-auto custom-scrollbar">
                                                    <FileExplorer files={fileList} onSelect={setSelectedFile} selectedPath={selectedFile || undefined} />
                                                </div>
                                            </div>

                                            {/* EDITOR AREA */}
                                            <div className="flex-1 relative bg-[#09090b]">
                                                {selectedFile ? (
                                                    <>
                                                        {/* Tabs/Breadcrumbs */}
                                                        <div className="h-9 border-b border-white/5 flex items-center px-4 gap-2 bg-zinc-900/20">
                                                            <span className="text-zinc-500 text-xs hover:text-zinc-300 cursor-pointer transition-colors">src</span>
                                                            <span className="text-zinc-700 text-[10px]">/</span>
                                                            <span className="text-zinc-300 text-xs font-medium">{selectedFile.split('/').pop()}</span>
                                                        </div>
                                                        <div className="flex-1 overflow-hidden h-[calc(100%-36px)]">
                                                            <CodeEditor code={files[selectedFile] || ""} language={getLanguage(selectedFile)} />
                                                        </div>
                                                    </>
                                                ) : (
                                                    <div className="h-full flex flex-col items-center justify-center text-zinc-800 gap-4">
                                                        <div className="w-16 h-16 rounded-full border border-zinc-800 flex items-center justify-center">
                                                            <Code className="w-6 h-6 opacity-20" />
                                                        </div>
                                                        <div className="text-[10px] font-black uppercase tracking-[0.5em] opacity-50">Select Module</div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )
                                ) : (
                                    /* Full-Screen Preview Housing */
                                    <div className="h-full w-full bg-black relative">
                                        {previewUrl ?
                                            <iframe src={previewUrl} className="h-full w-full border-none" />
                                            : (
                                                <div className="h-full w-full bg-[#050505] flex flex-col items-center justify-center gap-4">
                                                    <div className="w-8 h-8 border-2 border-zinc-800 border-t-zinc-400 rounded-full animate-spin" />
                                                    <div className="text-zinc-600 font-bold text-[10px] tracking-[0.3em] uppercase animate-pulse">Synchronizing Preview...</div>
                                                </div>
                                            )}
                                    </div>
                                )
                            ) : (
                                /* Grid Initial State - Live Agent Stage */
                                <div className="h-full w-full relative bg-black">
                                    <AgentStage logs={logs} className="w-full h-full" />
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Right Panel: Fixed Sidebar - Only visible in Code/Preview Mode */}
                    {showIDE && showLiveFeed && (
                        <div className="w-[20%] h-full animate-in slide-in-from-right duration-500 shrink-0 bg-zinc-950/50 backdrop-blur-md rounded-2xl border border-white/5 overflow-hidden">
                            <LiveFeed logs={logs} />
                        </div>
                    )}
                </div>
            </main>

            {/* Full-Screen VS Code Overlay */}
            {
                showFullScreenVSCode && vscodeUrl && (
                    <div className="fixed inset-0 z-[100] bg-black flex flex-col">
                        {/* Header Bar */}
                        <div className="h-12 bg-zinc-900 border-b border-zinc-700 flex items-center justify-between px-4 shrink-0">
                            <div className="flex items-center gap-4">
                                <button
                                    onClick={() => setShowFullScreenVSCode(false)}
                                    className="flex items-center gap-2 text-zinc-400 hover:text-white transition-colors text-sm font-medium"
                                >
                                    <X className="w-4 h-4" />
                                    Back to War Room
                                </button>
                                <span className="text-zinc-500 text-xs">|</span>
                                <span className="text-zinc-400 text-xs font-mono">
                                    Project: {projectId?.slice(0, 12)}...
                                </span>
                                <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-400 text-[10px] font-bold rounded uppercase">
                                    {projectType}
                                </span>
                            </div>

                            <div className="flex items-center gap-3">
                                {/* AI Features */}
                                <button
                                    onClick={handleDebug}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-amber-400 hover:text-amber-300 rounded-md text-xs font-medium transition-all border border-zinc-700"
                                >
                                    <Bug className="w-3.5 h-3.5" />
                                    AI Debug
                                </button>
                                <button
                                    onClick={handleGenerateDocs}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-violet-400 hover:text-violet-300 rounded-md text-xs font-medium transition-all border border-zinc-700"
                                >
                                    <FileText className="w-3.5 h-3.5" />
                                    Docs
                                </button>
                                <button
                                    onClick={handleDownload}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-sky-400 hover:text-sky-300 rounded-md text-xs font-medium transition-all border border-zinc-700"
                                >
                                    <Download className="w-3.5 h-3.5" />
                                    Download
                                </button>

                                <span className="text-zinc-600">|</span>

                                {/* Preview Link */}
                                {previewUrl && (
                                    <a
                                        href={previewUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-400 hover:text-cyan-300 rounded-md text-xs font-medium transition-all border border-cyan-600/30"
                                    >
                                        <Eye className="w-3.5 h-3.5" />
                                        Open Preview ↗
                                    </a>
                                )}

                                {/* Stop Button */}
                                <button
                                    onClick={handleStop}
                                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-950/50 hover:bg-red-900/50 text-red-400 hover:text-red-300 rounded-md text-xs font-medium transition-all border border-red-800/50"
                                >
                                    <Square className="w-3.5 h-3.5" />
                                    Stop
                                </button>
                            </div>
                        </div>

                        {/* VS Code iframe */}
                        <iframe
                            src={vscodeUrl}
                            className="flex-1 w-full border-none"
                            title="VS Code"
                            allow="clipboard-read; clipboard-write"
                            sandbox="allow-same-origin allow-scripts allow-forms allow-modals allow-downloads allow-popups"
                        />

                        {/* Welcome Banner */}
                        {showWelcomeBanner && (
                            <div className="absolute top-16 left-1/2 transform -translate-x-1/2 bg-gradient-to-r from-cyan-600 to-blue-600 text-white px-8 py-5 rounded-xl shadow-2xl z-50 max-w-lg animate-in slide-in-from-top duration-500">
                                <div className="flex items-start gap-4">
                                    <span className="text-3xl">👋</span>
                                    <div className="flex-1">
                                        <h3 className="font-bold text-lg mb-2">Welcome to Your VS Code Environment!</h3>
                                        <ul className="text-sm space-y-1.5 text-cyan-100">
                                            <li className="flex items-center gap-2">
                                                <span className="text-green-300">✅</span>
                                                Your {projectType} app is running on port {vsCodePort}
                                            </li>
                                            <li className="flex items-center gap-2">
                                                <span className="text-green-300">✅</span>
                                                Hot-reload enabled - edit and save to see changes
                                            </li>
                                            <li className="flex items-center gap-2">
                                                <span className="text-green-300">✅</span>
                                                Open terminal with <kbd className="px-1 py-0.5 bg-black/30 rounded text-xs font-mono">Ctrl+`</kbd>
                                            </li>
                                            <li className="flex items-center gap-2">
                                                <span className="text-green-300">✅</span>
                                                Check <code className="px-1 py-0.5 bg-black/30 rounded text-xs font-mono">INSTRUCTIONS.md</code> for more info
                                            </li>
                                        </ul>
                                        <button
                                            onClick={() => setShowWelcomeBanner(false)}
                                            className="mt-4 px-4 py-1.5 bg-white/20 hover:bg-white/30 text-white text-xs font-bold rounded-md transition-all"
                                        >
                                            Got it!
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Sandbox Status Indicator */}
                        <div className="absolute bottom-4 right-4 flex items-center gap-2 bg-black/80 backdrop-blur-sm px-3 py-1.5 rounded-full border border-emerald-500/30 z-50">
                            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                            <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">E2B Sandbox Active</span>
                        </div>
                    </div>
                )
            }
        </>
    )
}