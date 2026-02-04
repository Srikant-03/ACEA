"use client"

import { useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { LogEntry } from "@/types/socket"

interface LiveFeedProps {
    logs: LogEntry[]
}

export function LiveFeed({ logs }: LiveFeedProps) {
    const bottomRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [logs])

    return (
        <div className="h-full bg-black/80 font-mono text-sm p-4 rounded-lg border border-slate-800 overflow-hidden flex flex-col">
            <div className="flex items-center gap-2 mb-2 border-b border-slate-800 pb-2">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <span className="text-slate-400 uppercase tracking-widest text-xs">Live System Feed</span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-1 scrollbar-hide">
                <AnimatePresence>
                    {logs.map((log) => (
                        <motion.div
                            key={log.id}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            className="flex gap-3 text-xs"
                        >
                            <span className="text-slate-600 shrink-0">
                                {log.timestamp instanceof Date ? log.timestamp.toLocaleTimeString() : log.timestamp}
                            </span>
                            <span className={`w-20 shrink-0 font-bold ${log.agent === "SYSTEM" ? "text-purple-400" :
                                    log.agent === "ERROR" ? "text-red-500" : "text-cyan-500"
                                }`}>[{log.agent}]</span>
                            <span className={
                                log.type === 'error' ? 'text-red-400' :
                                    log.type === 'success' ? 'text-green-400' :
                                        log.type === 'warning' ? 'text-yellow-400' :
                                            'text-slate-300'
                            }>
                                {log.message}
                            </span>
                        </motion.div>
                    ))}
                </AnimatePresence>
                <div ref={bottomRef} />
            </div>
        </div>
    )
}
