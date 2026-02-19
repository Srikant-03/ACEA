import { Activity, CheckCircle, XCircle, Clock } from "lucide-react"

interface StatusPanelProps {
    agents: Record<string, "idle" | "running" | "success" | "error">;
}

export function StatusPanel({ agents }: StatusPanelProps) {
    return (
        <div className="bg-zinc-900/50 backdrop-blur-md rounded-xl border border-white/5 p-4 flex flex-col gap-4">
            <h3 className="text-xs font-bold font-orbitron text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <Activity className="w-4 h-4" /> System Status
            </h3>

            <div className="grid grid-cols-2 gap-3">
                {Object.entries(agents).map(([agent, status]) => (
                    <div key={agent} className={`
            relative p-3 rounded-lg border flex items-center justify-between group overflow-hidden transition-all
            ${status === 'running' ? 'bg-cyan-900/20 border-cyan-500/30 shadow-[0_0_15px_rgba(6,182,212,0.1)]' : ''}
            ${status === 'success' ? 'bg-emerald-900/10 border-emerald-500/20' : ''}
            ${status === 'error' ? 'bg-rose-900/10 border-rose-500/20' : ''}
            ${status === 'idle' ? 'bg-zinc-800/20 border-white/5' : ''}
          `}>

                        {/* Status indicator line */}
                        <div className={`absolute left-0 top-0 bottom-0 w-1 
              ${status === 'running' ? 'bg-cyan-400 shadow-[0_0_10px_#22d3ee]' : ''}
              ${status === 'success' ? 'bg-emerald-400' : ''}
              ${status === 'error' ? 'bg-rose-500' : ''}
              ${status === 'idle' ? 'bg-zinc-700' : ''}
            `} />

                        <div className="flex flex-col ml-2">
                            <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-300 group-hover:text-white transition-colors">
                                {agent}
                            </div>
                            <div className="text-[9px] font-mono opacity-60 uppercase">
                                {status}
                            </div>
                        </div>

                        <div className="status-icon">
                            {status === 'running' && <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />}
                            {status === 'success' && <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />}
                            {status === 'error' && <XCircle className="w-3.5 h-3.5 text-rose-400" />}
                            {status === 'idle' && <Clock className="w-3.5 h-3.5 text-zinc-600" />}
                        </div>

                        {/* Background scanner effect for running state */}
                        {status === 'running' && (
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/5 to-transparent -translate-x-full animate-shimmer pointer-events-none" />
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}
