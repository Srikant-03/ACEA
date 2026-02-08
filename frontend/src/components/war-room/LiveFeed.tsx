"use client"

import { useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { LogEntry } from "@/types/socket"
import { Terminal } from "lucide-react"
import { cn } from "@/lib/utils"

interface LiveFeedProps {
    logs: LogEntry[]
}

export function LiveFeed({ logs }: LiveFeedProps) {
    const endRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        endRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [logs])

    return (
        <div className="h-full w-full flex flex-col overflow-hidden bg-transparent">
            {/* Header */}
            <div className="flex items-center justify-between p-3 border-b border-white/5 bg-zinc-950/30">
                <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[10px] font-orbitron tracking-[0.2em] text-zinc-500 font-bold uppercase">System Logs</span>
                </div>
                <div className="flex gap-1">
                    {[1, 2, 3].map(i => <div key={i} className="w-1 h-1 rounded-full bg-zinc-800" />)}
                </div>
            </div>

            {/* Log Output */}
            <div className="flex-1 overflow-y-auto p-2 font-mono text-[10px] space-y-1 scrollbar-thin scrollbar-thumb-white/5 scrollbar-track-transparent">
                <AnimatePresence mode="popLayout" initial={false}>
                    {logs.length === 0 ? (
                        <motion.div
                            key="empty-state"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 0.5 }}
                            exit={{ opacity: 0 }}
                            className="text-zinc-600 text-center mt-10 italic"
                        >
                            Awaiting mission initialization...
                        </motion.div>
                    ) : (
                        logs.map((log) => (
                            <motion.div
                                key={log.id}
                                layout
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                className="flex gap-3 border-l-2 border-white/5 pl-3 py-0.5 hover:bg-white/5 transition-colors rounded-r"
                            >
                                <span className="text-zinc-500 shrink-0 select-none">
                                    {log.timestamp instanceof Date ? log.timestamp.toLocaleTimeString() : log.timestamp}
                                </span>
                                <span className={cn(
                                    "font-bold tracking-wide shrink-0",
                                    log.agent === "SYSTEM" ? "text-zinc-300" :
                                        log.agent === "ERROR" ? "text-rose-400" :
                                            "text-white"
                                )}>
                                    {log.agent}
                                </span>
                                <span className={cn(
                                    "break-all",
                                    log.type === 'error' ? "text-rose-300" :
                                        log.type === 'success' ? "text-emerald-300" :
                                            "text-zinc-400"
                                )}>
                                    {log.message}
                                </span>
                            </motion.div>
                        ))
                    )}
                </AnimatePresence>
                <div ref={endRef} />
            </div>

            {/* Scanline Effect - Subtle White */}
            <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(to_bottom,transparent_50%,rgba(255,255,255,0.02)_50%)] bg-[size:100%_4px]" />
        </div>
    )
}
