import { Terminal, ArrowDown } from "lucide-react"
import { useEffect, useRef } from "react"
import { Event } from "@/lib/events" // Correct import path

interface LogPanelProps {
    logs: any[]; // Changed to any for flexibility, ideally strictly typed but keeping compatible with existing page state
}

export function LogPanel({ logs }: LogPanelProps) {
    const scrollRef = useRef<HTMLDivElement>(null)

    // Auto-scroll to bottom on new logs
    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        }
    }, [logs])

    return (
        <div className="bg-black/80 backdrop-blur-md rounded-xl border border-white/10 flex flex-col h-full overflow-hidden shadow-2xl">
            <div className="h-10 border-b border-white/5 bg-zinc-900/50 flex items-center justify-between px-4">
                <div className="flex items-center gap-2 text-zinc-400">
                    <Terminal className="w-3.5 h-3.5" />
                    <span className="text-[10px] font-bold font-orbitron uppercase tracking-widest">Live Feed</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[9px] font-mono text-emerald-500/80 uppercase">Online</span>
                </div>
            </div>

            <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-1 font-mono text-xs custom-scrollbar">
                {logs.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-zinc-700 gap-2 opacity-50">
                        <Terminal className="w-8 h-8 opacity-20" />
                        <span className="text-[10px] uppercase tracking-widest">Awaiting Transmission...</span>
                    </div>
                ) : (
                    logs.map((log: any, i) => ( // Using any for compatibility with existing page state
                        <div key={i} className="flex gap-3 group hover:bg-white/5 py-0.5 px-2 rounded -mx-2 transition-colors">
                            <span className="text-zinc-600 shrink-0 text-[10px] w-14">{log.timestamp || new Date().toLocaleTimeString()}</span>
                            <span className={`
                    shrink-0 uppercase font-bold text-[10px] w-20 
                    ${log.type === 'error' ? 'text-rose-400' : ''}
                    ${log.type === 'success' ? 'text-emerald-400' : ''}
                    ${log.type === 'warning' ? 'text-amber-400' : ''}
                    ${log.type === 'info' ? 'text-cyan-400' : 'text-zinc-400'}
                `}>
                                {log.agent || "SYSTEM"}
                            </span>
                            <span className={`
                    text-zinc-300 break-words flex-1
                    ${log.type === 'error' ? 'text-rose-200' : ''}
                `}>
                                {log.message}
                            </span>
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}
