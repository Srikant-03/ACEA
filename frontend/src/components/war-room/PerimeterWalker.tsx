"use client"

import { motion, useAnimation } from "framer-motion"
import { useEffect, useState, useRef } from "react"
import { cn } from "@/lib/utils"

interface PerimeterWalkerProps {
    videos: string[] // Array of video paths
    className?: string
}

export function PerimeterWalker({ videos, className }: PerimeterWalkerProps) {
    const containerRef = useRef<HTMLDivElement>(null)
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
    const requestRef = useRef<number | null>(null)
    const [entities, setEntities] = useState<any[]>([])

    // Physics constants
    const SPEED = 80 // pixels per second
    const ENTITY_COUNT = 6
    const INSET = 20 // Distance from edge

    // Initialize/Resize observer
    useEffect(() => {
        if (!containerRef.current) return
        const obs = new ResizeObserver((entries) => {
            const { width, height } = entries[0].contentRect
            setDimensions({ width, height })
        })
        obs.observe(containerRef.current)
        return () => obs.disconnect()
    }, [])

    // Animation Loop
    useEffect(() => {
        if (dimensions.width === 0 || dimensions.height === 0) return

        const animate = (time: number) => {
            const w = dimensions.width
            const h = dimensions.height

            // Path segments (Top -> Right -> Bottom -> Left)
            // 0: Top (0,0 -> w,0) length: w
            // 1: Right (w,0 -> w,h) length: h
            // 2: Bottom (w,h -> 0,h) length: w
            // 3: Left (0,h -> 0,0) length: h
            const paramW = w - (INSET * 2)
            const paramH = h - (INSET * 2)
            const totalPerimeter = (paramW * 2) + (paramH * 2)

            // Calculate global progress based on time
            const loopDuration = (totalPerimeter / SPEED) * 1000 // ms
            const globalProgress = (time % loopDuration) / loopDuration

            const newEntities = Array.from({ length: 6 }).map((_, i) => { videoSrc: videos[i % videos.length] || "" })

            // Map entities
            const calculated = Array.from({ length: ENTITY_COUNT }).map((_, i) => {
                // Offset each entity evenly
                const offset = i / ENTITY_COUNT
                let progress = (globalProgress + offset) % 1

                // Determine position based on progress
                // Segments normalized: 
                // Top: 0 -> paramW / total
                // Right: paramW / total -> (paramW + paramH) / total
                // etc.

                const topEnd = paramW / totalPerimeter
                const rightEnd = (paramW + paramH) / totalPerimeter
                const bottomEnd = (2 * paramW + paramH) / totalPerimeter

                let x = 0, y = 0, rotate = 0, scaleX = 1

                if (progress < topEnd) {
                    // Top Edge (Moving Right)
                    const localP = progress / topEnd
                    x = INSET + localP * paramW
                    y = INSET
                    rotate = 0
                } else if (progress < rightEnd) {
                    // Right Edge (Moving Down)
                    const localP = (progress - topEnd) / (paramH / totalPerimeter)
                    x = w - INSET
                    y = INSET + localP * paramH
                    rotate = 90
                } else if (progress < bottomEnd) {
                    // Bottom Edge (Moving Left)
                    const localP = (progress - rightEnd) / (topEnd) // segment length is same as top
                    x = w - INSET - (localP * paramW)
                    y = h - INSET
                    rotate = 180
                    scaleX = 1 // Already rotated 180, so it's upside down. If we want head-inside, this is correct for "wall walking"
                } else {
                    // Left Edge (Moving Up)
                    const localP = (progress - bottomEnd) / (paramH / totalPerimeter)
                    x = INSET
                    y = h - INSET - (localP * paramH)
                    rotate = 270
                }

                return {
                    x, y, rotate, video: videos[i % videos.length]
                }
            })

            setEntities(calculated)
            requestRef.current = requestAnimationFrame(animate)
        }

        requestRef.current = requestAnimationFrame(animate)
        return () => {
            if (requestRef.current) cancelAnimationFrame(requestRef.current)
        }
    }, [dimensions, videos])

    return (
        <div ref={containerRef} className={cn("absolute inset-0 pointer-events-none overflow-hidden", className)}>
            {/* Draw 'Magnetic Rail' Path (Optional Visual) */}
            <div className="absolute inset-[20px] border border-white/5 rounded-sm opacity-30" />

            {entities.map((ent, i) => (
                <div
                    key={i}
                    className="absolute w-12 h-12 -ml-6 -mt-6 flex items-center justify-center transition-transform duration-75 will-change-transform"
                    style={{
                        transform: `translate(${ent.x}px, ${ent.y}px) rotate(${ent.rotate}deg)`
                    }}
                >
                    <div className="relative w-full h-full flex items-center justify-center">
                        {ent.video ? (
                            <video
                                src={ent.video}
                                autoPlay
                                loop
                                muted
                                playsInline
                                className="w-full h-full object-contain drop-shadow-[0_0_10px_rgba(0,0,0,0.8)]"
                            />
                        ) : (
                            // Fallback "Spirit"
                            <div className="w-5 h-8 bg-zinc-500/50 rounded-full blur-[2px] animate-pulse" />
                        )}
                    </div>
                </div>
            ))}
        </div>
    )
}
