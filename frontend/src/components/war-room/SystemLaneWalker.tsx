"use client"

import { useEffect, useState, useRef } from "react"
import { cn } from "@/lib/utils"

export interface WalkerEntity {
    video: string
    name: string
    intro: string
}

interface SystemLaneWalkerProps {
    entities: WalkerEntity[]
    className?: string
}

export function SystemLaneWalker({ entities, className }: SystemLaneWalkerProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const [width, setWidth] = useState(0)
    const requestRef = useRef<number | null>(null)

    // State for the single active walker
    const [activeWalker, setActiveWalker] = useState<{ x: number, data: WalkerEntity } | null>(null)
    const [isHovered, setIsHovered] = useState(false)

    // Animation state ref (mutable to avoid re-renders for logic)
    const state = useRef({
        phase: 'cooldown' as 'walking' | 'cooldown',
        nextSpawnTime: 0,
        currentIndex: 0,
        x: -50, // Start off-screen
        lastTime: 0
    })

    // Physics constants
    const SPEED = 25 // pixels per second (Slow & Calm)
    const WALKER_WIDTH = 100 // Increased width for larger presence

    // Resize observer
    useEffect(() => {
        if (!containerRef.current) return
        const obs = new ResizeObserver((entries) => {
            setWidth(entries[0].contentRect.width)
        })
        obs.observe(containerRef.current)
        return () => obs.disconnect()
    }, [])

    // Animation Loop
    useEffect(() => {
        if (width === 0 || !entities || entities.length === 0) return

        const animate = (time: number) => {
            if (!state.current.lastTime) state.current.lastTime = time
            const deltaTime = (time - state.current.lastTime) / 1000
            state.current.lastTime = time

            const s = state.current

            if (s.phase === 'cooldown') {
                if (time >= s.nextSpawnTime) {
                    // Spawn new walker
                    s.phase = 'walking'
                    s.x = -WALKER_WIDTH
                    s.currentIndex = (s.currentIndex + 1) % entities.length
                } else {
                    setActiveWalker(null)
                }
            } else if (s.phase === 'walking') {
                s.x += SPEED * deltaTime

                // Check if fully exited right side
                if (s.x > width) {
                    s.phase = 'cooldown'
                    // Cooldown: 2s to 4s
                    const cooldown = 2000 + Math.random() * 2000
                    s.nextSpawnTime = time + cooldown
                    setActiveWalker(null)
                } else {
                    setActiveWalker({
                        x: s.x,
                        data: entities[s.currentIndex]
                    })
                }
            }

            requestRef.current = requestAnimationFrame(animate)
        }

        requestRef.current = requestAnimationFrame(animate)
        return () => {
            if (requestRef.current) cancelAnimationFrame(requestRef.current)
        }
    }, [width, entities])

    return (
        <div ref={containerRef} className={cn("absolute bottom-0 left-0 w-full h-full bg-black overflow-visible flex items-center z-50", className)}>
            {/* Minimal Separation Line - Faint White/5 */}
            <div className="absolute top-0 left-0 w-full h-[1px] bg-white/5" />

            {/* NO Background Glow or Floor Effects */}

            {activeWalker && (
                <div
                    className="absolute top-0 h-full flex items-center justify-center transition-transform duration-75 will-change-transform group cursor-help"
                    style={{
                        transform: `translateX(${activeWalker.x}px)`,
                        width: `${WALKER_WIDTH}px`
                    }}
                    onMouseEnter={() => setIsHovered(true)}
                    onMouseLeave={() => setIsHovered(false)}
                >
                    {/* Tooltip - Appears on Hover - NO Background Glow */}
                    <div className={cn(
                        "absolute -top-12 left-1/2 -translate-x-1/2 bg-black/95 border border-white/10 rounded-lg px-3 py-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none whitespace-nowrap z-[100] shadow-xl",
                        "flex flex-col items-center gap-0.5"
                    )}>
                        <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">{activeWalker.data.name}</span>
                        <span className="text-[9px] text-slate-400 italic">"{activeWalker.data.intro}"</span>
                        {/* Tooltip Arrow */}
                        <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-black/95 border-r border-b border-white/10 rotate-45" />
                    </div>

                    <div className="relative w-full h-[90%] flex items-center justify-center transition-all duration-300">
                        {activeWalker.data.video ? (
                            <video
                                src={activeWalker.data.video}
                                autoPlay
                                loop
                                muted
                                playsInline
                                className="w-full h-full object-contain opacity-90 transition-opacity group-hover:opacity-100"
                            // Removed all drop-shadow classes
                            />
                        ) : (
                            <div className="w-3 h-5 bg-cyan-500/50 rounded-full blur-[1px] animate-pulse" />
                        )}

                        {/* NO Ground Reflection */}
                    </div>
                </div>
            )}
        </div>
    )
}
