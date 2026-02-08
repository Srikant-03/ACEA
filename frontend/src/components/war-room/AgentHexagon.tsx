"use client"

import { motion } from "framer-motion"
import { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface AgentHexagonProps {
  name: string
  status: "idle" | "working" | "success" | "error"
  icon: LucideIcon
  className?: string
}

export function AgentHexagon({ name, status, icon: Icon, className }: AgentHexagonProps) {
  const statusColors = {
    idle: "bg-white/5 text-zinc-500 border-white/5 shadow-none",
    working: "bg-white/10 text-zinc-200 border-white/20 shadow-[0_0_20px_rgba(255,255,255,0.1)]",
    success: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.1)]",
    error: "bg-rose-500/10 text-rose-300 border-rose-500/20 shadow-[0_0_15px_rgba(244,63,94,0.1)]",
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={cn("relative w-32 h-32 flex items-center justify-center", className)}
    >
      {/* Main Container - Dark Glass Slab */}
      <div
        className={cn(
          "absolute inset-0 rounded-2xl backdrop-blur-md transition-all duration-500 flex flex-col items-center justify-center gap-3 border",
          statusColors[status]
        )}
      >
        <Icon className={cn("w-6 h-6 transition-all duration-500", status === "working" ? "opacity-100 text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.5)]" : "opacity-60")} />
        <span className="text-[10px] font-orbitron font-bold tracking-[0.2em] uppercase opacity-80">{name}</span>
      </div>

      {/* Rotating outer ring for "working" state - Subtle Silver */}
      {status === "working" && (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          className="absolute inset-[-1px] rounded-2xl border border-white/20 border-dashed opacity-50 pointer-events-none"
        />
      )}

      {/* Pulse Effect for "working" state */}
      {status === "working" && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: [0, 0.2, 0], scale: 1.1 }}
          transition={{ duration: 2, repeat: Infinity }}
          className="absolute inset-0 bg-white rounded-2xl z-[-1]"
        />
      )}
    </motion.div>
  )
}
