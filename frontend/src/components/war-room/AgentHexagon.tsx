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
    idle: "border-slate-500 bg-slate-900/50 text-slate-400",
    working: "border-blue-500 bg-blue-900/50 text-blue-400 animate-pulse",
    success: "border-green-500 bg-green-900/50 text-green-400",
    error: "border-red-500 bg-red-900/50 text-red-400",
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      className={cn("relative w-32 h-36 flex items-center justify-center hexagon-clip", className)}
    >
      <div className={cn("absolute inset-0 border-2 hexagon-clip flex flex-col items-center justify-center gap-2 backdrop-blur-sm transition-colors duration-500", statusColors[status])}>
        <Icon className="w-8 h-8" />
        <span className="text-xs font-bold tracking-wider">{name}</span>
      </div>
      
      {/* Decorative rings for "working" state */}
      {status === "working" && (
        <motion.div
           animate={{ rotate: 360 }}
           transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
           className="absolute inset-0 border border-blue-500/30 rounded-full scale-125 border-dashed"
        />
      )}
    </motion.div>
  )
}
