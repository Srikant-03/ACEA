"use client"

import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/lib/utils"
import type { BrowserTestReport } from "@/components/preview/BrowserTestResults"
import { CheckCircle2, AlertTriangle, XCircle, Activity, Brain } from "lucide-react"

export interface AgentConfig {
    name: string
    video: string // Path to mp4
    role: string
    color: string // Tailwind text color class for name
}

interface AgentEntityProps {
    agent: AgentConfig
    thought: string | null
    position: { x: number, y: number } // Percentage 0-100
    className?: string
    status?: 'idle' | 'working' | 'success' | 'error'
    report?: BrowserTestReport | null
    thinkingSteps?: string[]
}

export function AgentEntity({ agent, thought, position, className, status = 'idle', report, thinkingSteps = [] }: AgentEntityProps) {
    const [isHovered, setIsHovered] = useState(false)

    // Determine glow color based on status
    const getStatusColor = () => {
        switch (status) {
            case 'working': return "shadow-[0_0_30px_rgba(6,182,212,0.6)] border-cyan-500/50"
            case 'success': return "shadow-[0_0_30px_rgba(34,197,94,0.6)] border-green-500/50"
            case 'error': return "shadow-[0_0_30px_rgba(239,68,68,0.6)] border-red-500/50"
            default: return "border-white/5" // Idle
        }
    }

    return (
        <motion.div
            className={cn("absolute w-32 h-32 flex flex-col items-center justify-center pointer-events-auto cursor-pointer", className)}
            style={{
                left: `${position.x}%`,
                top: `${position.y}%`
            }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{
                opacity: 1,
                scale: status === 'working' ? [1, 1.05, 1] : 1,
                y: [0, -10, 0] // Floating Idle Animation
            }}
            transition={{
                y: { duration: 4, repeat: Infinity, ease: "easeInOut" },
                scale: status === 'working' ? { duration: 1.5, repeat: Infinity, ease: "easeInOut" } : {},
                opacity: { duration: 0.5 }
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
        >
            {/* THOUGHT BUBBLE (Active) */}
            <AnimatePresence mode="wait">
                {thought && (
                    <motion.div
                        key="thought"
                        initial={{ opacity: 0, y: 10, scale: 0.8 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 5, scale: 0.9 }}
                        className="absolute -top-24 mb-2 z-50 pointer-events-none"
                    >
                        <div className="relative bg-zinc-900/95 backdrop-blur-md border border-cyan-500/30 px-4 py-3 rounded-2xl shadow-xl max-w-[220px]">
                            <div className="flex items-center gap-2 mb-1">
                                <Activity className="w-3 h-3 text-cyan-400 animate-pulse" />
                                <span className="text-[9px] font-bold text-cyan-300 uppercase tracking-wider">Processing</span>
                            </div>
                            <p className="text-[10px] text-zinc-200 font-mono leading-relaxed text-center">
                                {thought}
                            </p>
                            {/* Tiny Triangle Pointer */}
                            <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-zinc-900/95 border-r border-b border-cyan-500/30 rotate-45 transform" />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* HOVER INFO (Report, Thinking Steps, or Status) */}
            <AnimatePresence>
                {isHovered && !thought && (
                    <motion.div
                        initial={{ opacity: 0, y: 10, scale: 0.9 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute -top-28 z-[60] min-w-[220px]"
                    >
                        {report ? (
                            /* BROWSER REPORT MINI-CARD */
                            <div className="bg-zinc-950/90 backdrop-blur-xl border border-white/10 p-3 rounded-xl shadow-2xl">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-[10px] font-bold uppercase text-zinc-400">Latest Validation</span>
                                    <span className={cn(
                                        "text-[10px] font-bold px-1.5 py-0.5 rounded",
                                        report.overall_status === 'EXCELLENT' || report.overall_status === 'GOOD' ? "bg-emerald-500/20 text-emerald-400" :
                                            report.overall_status === 'WARN' ? "bg-amber-500/20 text-amber-400" : "bg-red-500/20 text-red-400"
                                    )}>
                                        {report.overall_status}
                                    </span>
                                </div>
                                <div className="space-y-1">
                                    <div className="flex justify-between text-[10px]">
                                        <span className="text-zinc-500">Score</span>
                                        <span className="text-zinc-200">{report.scores?.overall ?? 'N/A'}/100</span>
                                    </div>
                                    <div className="flex justify-between text-[10px]">
                                        <span className="text-zinc-500">Issues</span>
                                        <span className="text-zinc-200">{report.total_issues}</span>
                                    </div>
                                </div>
                            </div>
                        ) : thinkingSteps.length > 0 ? (
                            /* THINKING STEPS CARD */
                            <div className="bg-zinc-950/95 backdrop-blur-xl border border-white/10 p-3 rounded-xl shadow-2xl max-h-[200px] overflow-y-auto">
                                <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-white/5">
                                    <Brain className="w-3 h-3 text-purple-400" />
                                    <span className="text-[9px] font-bold text-purple-300 uppercase tracking-widest">
                                        {agent.role}&apos;s Thinking
                                    </span>
                                    <span className={cn(
                                        "ml-auto text-[8px] font-bold px-1 py-0.5 rounded-full",
                                        status === 'working' ? "bg-cyan-500/20 text-cyan-300" :
                                            status === 'success' ? "bg-emerald-500/20 text-emerald-300" :
                                                status === 'error' ? "bg-red-500/20 text-red-300" :
                                                    "bg-zinc-500/20 text-zinc-400"
                                    )}>
                                        {status}
                                    </span>
                                </div>
                                <div className="space-y-1">
                                    {thinkingSteps.slice(-8).map((step, i, arr) => (
                                        <div key={i} className="flex items-start gap-2">
                                            <div className="flex flex-col items-center shrink-0 mt-1">
                                                <div className={`w-1.5 h-1.5 rounded-full ${i === arr.length - 1 ? 'bg-cyan-400' : 'bg-zinc-600'}`} />
                                                {i < arr.length - 1 && <div className="w-px h-3 bg-zinc-700" />}
                                            </div>
                                            <p className={`text-[10px] leading-relaxed ${i === arr.length - 1 ? 'text-zinc-200' : 'text-zinc-500'}`}>
                                                {step}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            /* STANDARD STATUS CARD */
                            <div className="bg-zinc-900/90 backdrop-blur-md border border-white/10 px-3 py-2 rounded-xl shadow-xl flex flex-col items-center">
                                <span className={cn("text-[10px] font-bold uppercase tracking-widest mb-1", agent.color)}>
                                    {agent.role}
                                </span>
                                <div className="flex items-center gap-1.5">
                                    <div className={cn("w-1.5 h-1.5 rounded-full",
                                        status === 'working' ? "bg-cyan-400 animate-pulse" :
                                            status === 'success' ? "bg-emerald-400" :
                                                status === 'error' ? "bg-red-400" : "bg-zinc-600"
                                    )} />
                                    <span className="text-[10px] text-zinc-400 font-mono capitalize">{status}</span>
                                </div>
                            </div>
                        )}
                        {/* Pointer */}
                        <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-zinc-900/90 border-r border-b border-white/10 rotate-45 transform" />
                    </motion.div>
                )}
            </AnimatePresence>

            {/* AVATAR / VIDEO */}
            <div className={cn(
                "relative w-full h-full flex items-center justify-center rounded-full transition-all duration-500 border",
                getStatusColor()
            )}>
                {/* Agent Name Tag */}
                <div className="absolute -bottom-8 bg-black/60 backdrop-blur-md border border-white/10 px-3 py-1 rounded-full z-10 hover:scale-105 transition-transform">
                    <span className={cn("text-[9px] font-orbitron font-bold tracking-widest uppercase", agent.color)}>
                        {agent.name}
                    </span>
                    {status === 'success' && <CheckCircle2 className="w-3 h-3 text-emerald-500 absolute -right-1 -top-1 bg-black rounded-full" />}
                    {status === 'error' && <XCircle className="w-3 h-3 text-red-500 absolute -right-1 -top-1 bg-black rounded-full" />}
                    {status === 'working' && <Activity className="w-3 h-3 text-cyan-400 absolute -right-1 -top-1 bg-black rounded-full animate-pulse" />}
                </div>

                <div className="w-full h-full relative rounded-full overflow-hidden">
                    {agent.video.endsWith('.gif') ? (
                        <img
                            src={agent.video}
                            alt={agent.name}
                            className="w-full h-full object-cover opacity-90 hover:opacity-100 transition-opacity"
                        />
                    ) : (
                        <video
                            src={agent.video}
                            autoPlay
                            loop
                            muted
                            playsInline
                            className="w-full h-full object-cover opacity-90 hover:opacity-100 transition-opacity"
                        />
                    )}
                </div>
            </div>
        </motion.div>
    )
}
