import { History, Play, Pause, SkipBack, SkipForward } from "lucide-react"
import { AgentState } from "@/lib/events"

interface TimeTravelProps {
    states: AgentState[];
    currentIdx: number;
    onNavigate: (idx: number) => void;
}

export function TimeTravel({ states, currentIdx, onNavigate }: TimeTravelProps) {
    if (states.length === 0) return null

    return (
        <div className="bg-zinc-900/80 backdrop-blur-md rounded-xl border border-white/5 p-4 flex flex-col gap-3 shadow-xl">
            <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold font-orbitron text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                    <History className="w-3.5 h-3.5" /> Temporal State
                </h3>
                <span className="text-[9px] font-mono text-zinc-500 bg-black/40 px-2 py-0.5 rounded border border-white/5">
                    SNAPSHOT {currentIdx + 1} / {states.length}
                </span>
            </div>

            <div className="flex items-center gap-4">
                {/* Timeline Slider */}
                <input
                    type="range"
                    min={0}
                    max={states.length - 1}
                    value={currentIdx}
                    onChange={(e) => onNavigate(parseInt(e.target.value))}
                    className="flex-1 h-1.5 bg-zinc-800 rounded-full appearance-none cursor-pointer accent-cyan-500 hover:accent-cyan-400 transition-all"
                />

                <div className="flex gap-1 shrink-0">
                    <button
                        onClick={() => onNavigate(Math.max(0, currentIdx - 1))}
                        disabled={currentIdx <= 0}
                        className="p-1.5 hover:bg-white/10 rounded disabled:opacity-30 transition-colors text-zinc-300"
                    >
                        <SkipBack className="w-3 h-3" />
                    </button>
                    <button
                        onClick={() => onNavigate(Math.min(states.length - 1, currentIdx + 1))}
                        disabled={currentIdx >= states.length - 1}
                        className="p-1.5 hover:bg-white/10 rounded disabled:opacity-30 transition-colors text-zinc-300"
                    >
                        <SkipForward className="w-3 h-3" />
                    </button>
                </div>
            </div>

            {/* Brief State Preview */}
            <div className="bg-black/40 rounded border border-white/5 p-2 text-[10px] font-mono text-zinc-400 truncate">
                <span className="text-cyan-600 font-bold mr-2">LAST ACTION:</span>
                {states[currentIdx]?.current_status || "Unknown"}
                {states[currentIdx]?.run_id ? ` [RUN: ${states[currentIdx].run_id.slice(0, 8)}]` : ''}
            </div>
        </div>
    )
}
