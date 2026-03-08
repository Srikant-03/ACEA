"use client"

import { useState } from "react"
import { Activity, CheckCircle, XCircle, Clock, ChevronRight, Brain } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

interface StatusPanelProps {
    agents: Record<string, "idle" | "running" | "success" | "error">;
    agentLogs?: Record<string, string[]>;
}

// Friendly display names
const AGENT_DISPLAY: Record<string, { label: string; emoji: string }> = {
    ARCHITECT: { label: "Architect", emoji: "🧠" },
    VIRTUOSO: { label: "Virtuoso", emoji: "⚡" },
    SENTINEL: { label: "Sentinel", emoji: "🛡️" },
    ORACLE: { label: "Oracle", emoji: "🔮" },
    WATCHER: { label: "Watcher", emoji: "👁️" },
    ADVISOR: { label: "Advisor", emoji: "📋" },
    BROWSER_VALIDATOR: { label: "Browser QA", emoji: "🌐" },
    SYSTEM: { label: "System", emoji: "⚙️" },
}

export function StatusPanel({ agents, agentLogs = {} }: StatusPanelProps) {
    const [hoveredAgent, setHoveredAgent] = useState<string | null>(null)

    return (
        <div className="bg-zinc-900/50 backdrop-blur-md rounded-xl border border-white/5 p-4 flex flex-col gap-4">
            <h3 className="text-xs font-bold font-orbitron text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Activity className="w-4 h-4" /> System Status
            </h3>

            <div className="grid grid-cols-2 gap-2">
                {Object.entries(agents).map(([agent, status]) => {
                    const display = AGENT_DISPLAY[agent] || { label: agent, emoji: "🤖" }
                    const steps = agentLogs[agent] || []
                    const isHovered = hoveredAgent === agent

                    return (
                        <div
                            key={agent}
                            className="relative"
                            onMouseEnter={() => setHoveredAgent(agent)}
                            onMouseLeave={() => setHoveredAgent(null)}
                        >
                            {/* --- Agent Card --- */}
                            <div className={`
                                relative p-2.5 rounded-lg border flex items-center justify-between
                                transition-all duration-300 cursor-pointer overflow-hidden
                                ${status === 'running'
                                    ? 'bg-cyan-950/40 border-cyan-500/40 shadow-[0_0_20px_rgba(6,182,212,0.15)] scale-[1.02]'
                                    : ''}
                                ${status === 'success' ? 'bg-emerald-950/20 border-emerald-500/20' : ''}
                                ${status === 'error' ? 'bg-rose-950/20 border-rose-500/20' : ''}
                                ${status === 'idle' ? 'bg-zinc-800/20 border-white/5 hover:border-white/10' : ''}
                            `}>
                                {/* Left accent bar */}
                                <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l transition-colors
                                    ${status === 'running' ? 'bg-cyan-400 shadow-[0_0_8px_#22d3ee]' : ''}
                                    ${status === 'success' ? 'bg-emerald-400' : ''}
                                    ${status === 'error' ? 'bg-rose-500' : ''}
                                    ${status === 'idle' ? 'bg-zinc-700' : ''}
                                `} />

                                <div className="flex flex-col ml-2 min-w-0">
                                    <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-200 flex items-center gap-1.5">
                                        <span>{display.emoji}</span>
                                        <span className="truncate">{display.label}</span>
                                    </div>
                                    <div className={`text-[9px] font-mono uppercase mt-0.5 flex items-center gap-1
                                        ${status === 'running' ? 'text-cyan-400' : ''}
                                        ${status === 'success' ? 'text-emerald-400' : ''}
                                        ${status === 'error' ? 'text-rose-400' : ''}
                                        ${status === 'idle' ? 'text-zinc-600' : ''}
                                    `}>
                                        {status === 'running' && <span className="inline-block w-1 h-1 rounded-full bg-cyan-400 animate-pulse" />}
                                        {status}
                                    </div>
                                </div>

                                {/* Status icon */}
                                <div className="shrink-0">
                                    {status === 'running' && <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />}
                                    {status === 'success' && <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />}
                                    {status === 'error' && <XCircle className="w-3.5 h-3.5 text-rose-400" />}
                                    {status === 'idle' && <Clock className="w-3.5 h-3.5 text-zinc-600" />}
                                </div>

                                {/* Shimmer for running */}
                                {status === 'running' && (
                                    <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent animate-shimmer pointer-events-none" />
                                )}

                                {/* Expand hint */}
                                {steps.length > 0 && (
                                    <ChevronRight className={`w-3 h-3 text-zinc-600 absolute right-1.5 top-1.5 transition-transform ${isHovered ? 'rotate-90 text-zinc-400' : ''}`} />
                                )}
                            </div>

                            {/* --- Hover Tooltip: Thinking Steps --- */}
                            <AnimatePresence>
                                {isHovered && steps.length > 0 && (
                                    <motion.div
                                        initial={{ opacity: 0, y: -4, scale: 0.95 }}
                                        animate={{ opacity: 1, y: 0, scale: 1 }}
                                        exit={{ opacity: 0, y: -4, scale: 0.95 }}
                                        transition={{ duration: 0.15 }}
                                        className="absolute z-[100] left-0 right-0 top-full mt-1"
                                    >
                                        <div className="bg-zinc-950/95 backdrop-blur-xl border border-white/10 rounded-xl p-3 shadow-2xl max-h-[200px] overflow-y-auto">
                                            <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-white/5">
                                                <Brain className="w-3 h-3 text-purple-400" />
                                                <span className="text-[9px] font-bold text-purple-300 uppercase tracking-widest">
                                                    {display.label}&apos;s Thinking
                                                </span>
                                            </div>

                                            <div className="space-y-1.5">
                                                {steps.map((step, i) => (
                                                    <div key={i} className="flex items-start gap-2">
                                                        {/* Timeline dot + line */}
                                                        <div className="flex flex-col items-center shrink-0 mt-1">
                                                            <div className={`w-1.5 h-1.5 rounded-full ${i === steps.length - 1 ? 'bg-cyan-400' : 'bg-zinc-600'}`} />
                                                            {i < steps.length - 1 && <div className="w-px h-3 bg-zinc-700" />}
                                                        </div>
                                                        <p className={`text-[10px] leading-relaxed ${i === steps.length - 1 ? 'text-zinc-200' : 'text-zinc-500'}`}>
                                                            {step}
                                                        </p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
