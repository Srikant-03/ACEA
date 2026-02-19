import { BarChart, Zap, Layers, Cpu } from "lucide-react"

interface MetricsDashboardProps {
    data: any; // Flexible for now
}

export function MetricsDashboard({ data }: MetricsDashboardProps) {
    // Default metrics or derived from data
    const metrics = [
        { label: "Steps", value: data?.steps || 0, icon: Layers, color: "text-blue-400" },
        { label: "Latency", value: `${data?.latency || 0}ms`, icon: Zap, color: "text-yellow-400" },
        { label: "Tokens", value: data?.tokens || 0, icon: Cpu, color: "text-purple-400" },
    ]

    return (
        <div className="bg-zinc-900/50 backdrop-blur-md rounded-xl border border-white/5 p-4 flex flex-col gap-4">
            <h3 className="text-xs font-bold font-orbitron text-zinc-400 uppercase tracking-widest flex items-center gap-2">
                <BarChart className="w-4 h-4" /> Telemetry
            </h3>

            <div className="grid grid-cols-3 gap-2">
                {metrics.map((m, i) => (
                    <div key={i} className="bg-black/30 border border-white/5 rounded-lg p-2 flex flex-col items-center justify-center text-center">
                        <m.icon className={`w-3 h-3 mb-1 ${m.color}`} />
                        <div className="text-sm font-bold text-zinc-200">{m.value}</div>
                        <div className="text-[8px] text-zinc-600 uppercase tracking-wider">{m.label}</div>
                    </div>
                ))}
            </div>
        </div>
    )
}
