"use client"

import { useEffect, useState, useRef } from "react"
import { AgentEntity, AgentConfig } from "./AgentEntity"
import { LogEntry, AgentsState } from "@/types/socket" // Import AgentsState
import { BrowserTestReport } from "@/components/preview/BrowserTestResults" // Import BrowserTestReport

// STATIC CONFIGURATION FOR AGENTS
const AGENTS: AgentConfig[] = [
    { name: "ARCHITECT", role: "Design", video: "/videos/bob.gif", color: "text-purple-400" },
    { name: "VIRTUOSO", role: "Execute", video: "/videos/chib.gif", color: "text-blue-400" },
    { name: "SENTINEL", role: "Security", video: "/videos/Shesu.gif", color: "text-red-400" },
    { name: "ORACLE", role: "Data", video: "/videos/Sett.gif", color: "text-amber-400" },
    { name: "WATCHER", role: "Monitor", video: "/videos/eww.gif", color: "text-emerald-400" },
    { name: "ADVISOR", role: "Guide", video: "/videos/eart.gif", color: "text-pink-400" },
    { name: "BROWSER_VALIDATOR", role: "QA", video: "/videos/Eyes.mp4", color: "text-cyan-400" }, // Added QA Agent
]

interface AgentStageProps {
    logs: LogEntry[]
    className?: string
    agents?: Partial<AgentsState> // New Prop
    browserTestResults?: BrowserTestReport | null // New Prop
    agentLogs?: Record<string, string[]> // Thinking history per agent
}

// Physics Constants
const SPEED = 0.05 // Base speed factor
const REPULSION_DIST = 15 // Distance (in %) to start repelling
const REPULSION_FORCE = 0.005
const BOUNDS_PADDING = 10 // Keep away from edges (%)
const WANDER_STRENGTH = 0.002 // Random direction change

export function AgentStage({ logs, className, agents = {}, browserTestResults, agentLogs = {} }: AgentStageProps) {
    const [thoughts, setThoughts] = useState<Record<string, string>>({})

    // Physics State stored in Ref to avoid React render loop lag, but we sync to State for render
    const INITIAL_AGENTS_STATE = AGENTS.map(() => ({
        x: 50,
        y: 50,
        vx: 0,
        vy: 0
    }))

    const physicsState = useRef(INITIAL_AGENTS_STATE)

    // Render State
    const [positions, setPositions] = useState(INITIAL_AGENTS_STATE)
    const [mounted, setMounted] = useState(false)
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
        // Map BROWSER_TEST log to BROWSER_VALIDATOR agent
        const mappedName = agentName === 'BROWSER_TEST' ? 'BROWSER_VALIDATOR' : agentName

        const matchedAgent = AGENTS.find(a => a.name === mappedName)

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
        const currentTimeouts = timeouts.current
        return () => Object.values(currentTimeouts).forEach(t => clearTimeout(t))
    }, [])

    // INITIALIZE RANDOM POSITIONS (Client Only)
    useEffect(() => {
        physicsState.current = AGENTS.map(() => ({
            x: 20 + Math.random() * 60,
            y: 20 + Math.random() * 60,
            vx: (Math.random() - 0.5) * SPEED,
            vy: (Math.random() - 0.5) * SPEED
        }))
        setMounted(true)
    }, [])

    // PHYSICS LOOP
    useEffect(() => {
        const animate = () => {
            // Update Physics
            physicsState.current = physicsState.current.map((agent, i, allAgents) => {
                const { x, y } = agent
                let { vx, vy } = agent

                // 1. Repulsion from Peers
                allAgents.forEach((peer, j) => {
                    if (i === j) return
                    const dx = x - peer.x
                    const dy = y - peer.y
                    const dist = Math.sqrt(dx * dx + dy * dy)

                    if (dist < REPULSION_DIST && dist > 0) {
                        const force = (REPULSION_DIST - dist) * REPULSION_FORCE
                        vx += (dx / dist) * force
                        vy += (dy / dist) * force
                    }
                })

                // 2. Center Gravity (Weak pull to center)
                const dxC = 50 - x
                const dyC = 50 - y
                vx += dxC * 0.00005
                vy += dyC * 0.00005

                // 3. Wander (Random jitter)
                vx += (Math.random() - 0.5) * WANDER_STRENGTH
                vy += (Math.random() - 0.5) * WANDER_STRENGTH

                // 4. Update Position
                let newX = x + vx
                let newY = y + vy

                // 5. Bounds Check (Bounce)
                if (newX < BOUNDS_PADDING || newX > 100 - BOUNDS_PADDING) vx = -vx
                if (newY < BOUNDS_PADDING || newY > 100 - BOUNDS_PADDING) vy = -vy

                // 6. Damping (Friction)
                vx *= 0.99
                vy *= 0.99

                return { x: newX, y: newY, vx, vy }
            })

            setPositions([...physicsState.current])
            requestRef.current = requestAnimationFrame(animate)
        }

        requestRef.current = requestAnimationFrame(animate)
        return () => {
            if (requestRef.current) cancelAnimationFrame(requestRef.current)
        }
    }, [])

    if (!mounted) return null

    return (
        <div className={className}>
            {AGENTS.map((agent, i) => {
                // Determine Status: Prioritize 'working' if thought is active
                let status: 'idle' | 'working' | 'success' | 'error' = 'idle'

                // If thought is active, force working
                if (thoughts[agent.name]) {
                    status = 'working'
                } else {
                    // Use backend status if available, fallback to idle
                    const backendStatus = agents[agent.name as keyof AgentsState]
                    if (backendStatus) status = backendStatus
                }

                // Pass report only to BROWSER_VALIDATOR
                const report = agent.name === 'BROWSER_VALIDATOR' ? browserTestResults : undefined

                return (
                    <AgentEntity
                        key={agent.name}
                        agent={agent}
                        thought={thoughts[agent.name] || null}
                        position={{ x: positions[i].x, y: positions[i].y }}
                        status={status}
                        report={report}
                        thinkingSteps={agentLogs[agent.name] || []}
                    />
                )
            })}
        </div>
    )
}
