"use client"

import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/lib/utils"

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
}

export function AgentEntity({ agent, thought, position, className }: AgentEntityProps) {
    return (
        <motion.div
            className={cn("absolute w-32 h-32 flex flex-col items-center justify-center pointer-events-none", className)}
            style={{
                left: `${position.x}%`,
                top: `${position.y}%`
            }}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{
                opacity: 1,
                scale: 1,
                y: [0, -10, 0] // Floating Idle Animation
            }}
            transition={{
                y: { duration: 4, repeat: Infinity, ease: "easeInOut" },
                opacity: { duration: 0.5 }
            }}
        >
            {/* THOUGHT BUBBLE */}
            <AnimatePresence mode="wait">
                {thought && (
                    <motion.div
                        key="thought"
                        initial={{ opacity: 0, y: 10, scale: 0.8 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 5, scale: 0.9 }}
                        className="absolute -top-24 mb-2 z-50 pointer-events-auto"
                    >
                        <div className="relative bg-zinc-900/90 backdrop-blur-md border border-white/10 px-4 py-3 rounded-2xl shadow-xl max-w-[200px]">
                            <p className="text-[10px] text-zinc-200 font-mono leading-relaxed text-center">
                                {thought}
                            </p>

                            {/* Tiny Triangle Pointer */}
                            <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-zinc-900/90 border-r border-b border-white/10 rotate-45 transform" />
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* AVATAR / VIDEO */}
            <div className="relative w-full h-full flex items-center justify-center">
                {/* Agent Name Tag (Always visible, subtle) */}
                <div className="absolute -bottom-8 bg-black/40 backdrop-blur-sm border border-white/5 px-3 py-1 rounded-full">
                    <span className={cn("text-[9px] font-orbitron font-bold tracking-widest uppercase", agent.color)}>
                        {agent.name}
                    </span>
                </div>

                <div className="w-full h-full relative">
                    {agent.video.endsWith('.gif') ? (
                        <img
                            src={agent.video}
                            alt={agent.name}
                            className="w-full h-full object-contain mix-blend-screen opacity-100 drop-shadow-2xl"
                        />
                    ) : (
                        <video
                            src={agent.video}
                            autoPlay
                            loop
                            muted
                            playsInline
                            className="w-full h-full object-contain mix-blend-screen opacity-100 drop-shadow-2xl"
                        />
                    )}
                </div>
            </div>
        </motion.div>
    )
}
