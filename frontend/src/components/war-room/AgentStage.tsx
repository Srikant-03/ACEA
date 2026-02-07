"use client"

import { useEffect, useState, useRef } from "react"
import { AgentEntity, AgentConfig } from "./AgentEntity"
import { LogEntry } from "@/types/socket"

// STATIC CONFIGURATION FOR AGENTS
const AGENTS: AgentConfig[] = [
    { name: "ARCHITECT", role: "Design", video: "/videos/bob.gif", color: "text-zinc-300" },
    { name: "VIRTUOSO", role: "Execute", video: "/videos/chib.gif", color: "text-zinc-300" },
    { name: "SENTINEL", role: "Security", video: "/videos/Shesu.gif", color: "text-zinc-300" },
    { name: "ORACLE", role: "Data", video: "/videos/Sett.gif", color: "text-zinc-300" },
    { name: "WATCHER", role: "Monitor", video: "/videos/eww.gif", color: "text-zinc-300" },
    { name: "ADVISOR", role: "Guide", video: "/videos/eart.gif", color: "text-zinc-300" },
]

interface AgentStageProps {
    logs: LogEntry[]
    className?: string
}

// Physics Constants
const SPEED = 0.05 // Base speed factor
const REPULSION_DIST = 15 // Distance (in %) to start repelling
const REPULSION_FORCE = 0.005
const BOUNDS_PADDING = 10 // Keep away from edges (%)
const WANDER_STRENGTH = 0.002 // Random direction change

export function AgentStage({ logs, className }: AgentStageProps) {
    const [thoughts, setThoughts] = useState<Record<string, string>>({})

    // Physics State stored in Ref to avoid React render loop lag, but we sync to State for render
    // Using Ref for calculation, State for commit
    const physicsState = useRef(AGENTS.map(() => ({
        x: 20 + Math.random() * 60, // Start somewhat centered
        y: 20 + Math.random() * 60,
        vx: (Math.random() - 0.5) * SPEED,
        vy: (Math.random() - 0.5) * SPEED
    })))

    // Render State
    const [positions, setPositions] = useState(physicsState.current)
    const requestRef = useRef<number | null>(null)

    // Log Logic State
    const lastProcessedLogId = useRef<number | string | null>(null)
    const timeouts = useRef<Record<string, NodeJS.Timeout>>({})

    // LOG PROCESSING
    useEffect(() => {
        if (!logs.length) return
        const latestLog = logs[logs.length - 1]

        if (latestLog.id === lastProcessedLogId.current) return
        lastProcessedLogId.current = latestLog.id

        const agentName = latestLog.agent
        const matchedAgent = AGENTS.find(a => a.name === agentName)

        if (matchedAgent) {
            setThoughts(prev => ({ ...prev, [matchedAgent.name]: latestLog.message }))
            if (timeouts.current[matchedAgent.name]) clearTimeout(timeouts.current[matchedAgent.name])
            timeouts.current[matchedAgent.name] = setTimeout(() => {
                setThoughts(prev => {
                    const next = { ...prev }
                    delete next[matchedAgent.name]
                    return next
                })
            }, 4000)
        }
    }, [logs])

    // Cleanup timeouts
    useEffect(() => {
        return () => Object.values(timeouts.current).forEach(t => clearTimeout(t))
    }, [])

    // PHYSICS LOOP
    useEffect(() => {
        const animate = () => {
            // Update Physics
            physicsState.current = physicsState.current.map((agent, i, allAgents) => {
                let { x, y, vx, vy } = agent

                // 1. Wander (Random small pushes)
                vx += (Math.random() - 0.5) * WANDER_STRENGTH
                vy += (Math.random() - 0.5) * WANDER_STRENGTH

                // Cap Velocity (Speed Limit)
                const speed = Math.sqrt(vx * vx + vy * vy)
                if (speed > SPEED) {
                    vx = (vx / speed) * SPEED
                    vy = (vy / speed) * SPEED
                }

                // 2. Repulsion (Avoid other agents)
                allAgents.forEach((other, j) => {
                    if (i === j) return
                    const dx = x - other.x
                    const dy = y - other.y
                    const dist = Math.sqrt(dx * dx + dy * dy)

                    if (dist < REPULSION_DIST && dist > 0) {
                        const force = (REPULSION_DIST - dist) * REPULSION_FORCE
                        vx += (dx / dist) * force
                        vy += (dy / dist) * force
                    }
                })

                // 3. Update Position
                let newX = x + vx
                let newY = y + vy

                // 4. Boundary Bounce & Containment
                if (newX < BOUNDS_PADDING) { newX = BOUNDS_PADDING; vx *= -1 }
                if (newX > 100 - BOUNDS_PADDING) { newX = 100 - BOUNDS_PADDING; vx *= -1 }
                if (newY < BOUNDS_PADDING) { newY = BOUNDS_PADDING; vy *= -1 }
                if (newY > 100 - BOUNDS_PADDING) { newY = 100 - BOUNDS_PADDING; vy *= -1 }

                return { x: newX, y: newY, vx, vy }
            })

            // Commit to Render State
            setPositions([...physicsState.current])

            requestRef.current = requestAnimationFrame(animate)
        }

        requestRef.current = requestAnimationFrame(animate)
        return () => {
            if (requestRef.current) cancelAnimationFrame(requestRef.current)
        }
    }, [])

    return (
        <div className={`relative w-full h-full ${className}`}>
            {/* Background Decorations */}
            <div className="absolute inset-0 pointer-events-none opacity-5">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[60%] h-[60%] border border-zinc-700/30 rounded-full animate-[spin_60s_linear_infinite]" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[40%] h-[40%] border border-zinc-700/20 rounded-full border-dashed animate-[spin_40s_linear_infinite_reverse]" />
            </div>

            {AGENTS.map((agent, index) => (
                <AgentEntity
                    key={agent.name}
                    agent={agent}
                    thought={thoughts[agent.name] || null}
                    position={positions[index]}
                />
            ))}
        </div>
    )
}
