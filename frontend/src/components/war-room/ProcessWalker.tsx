"use client"

import { motion, useAnimation } from "framer-motion"
import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

interface ProcessWalkerProps {
    videoSrc?: string // Optional, user will add later
    lane: number // 1, 2, or 3
    color: string // Fallback/Glow color
    className?: string
}

export function ProcessWalker({ videoSrc, lane, color, className }: ProcessWalkerProps) {
    const controls = useAnimation()
    const [direction, setDirection] = useState<'right' | 'left'>('right')

    // Lane positioning configuration
    const laneConfig = {
        1: { top: '15%', zIndex: 10, scale: 0.8, speed: 25 },
        2: { top: '45%', zIndex: 20, scale: 0.9, speed: 35 },
        3: { top: '75%', zIndex: 30, scale: 1.0, speed: 30 }
    }

    const config = laneConfig[lane as keyof typeof laneConfig] || laneConfig[1]

    useEffect(() => {
        const patrol = async () => {
            // Randomize start position slightly to desync walkers
            const startX = Math.random() * 80
            await controls.set({ x: `${startX}%` })

            while (true) {
                // Walk Right
                setDirection('right')
                const durationRight = (100 - startX) / config.speed * (Math.random() * 0.5 + 4) // Variable duration
                await controls.start({
                    x: "90%",
                    transition: { duration: durationRight, ease: "linear" }
                })

                // Pause at right end
                await new Promise(r => setTimeout(r, Math.random() * 2000 + 1000))

                // Walk Left
                setDirection('left')
                const durationLeft = 100 / config.speed * (Math.random() * 0.5 + 4)
                await controls.start({
                    x: "10%",
                    transition: { duration: durationLeft, ease: "linear" }
                })

                // Pause at left end
                await new Promise(r => setTimeout(r, Math.random() * 2000 + 1000))
            }
        }

        patrol()
    }, [controls, config.speed])

    return (
        <motion.div
            animate={controls}
            className={cn("absolute left-0 w-12 h-12 flex items-center justify-center pointer-events-auto cursor-pointer group", className)}
            style={{
                top: config.top,
                zIndex: config.zIndex,
                scale: config.scale
            }}
            whileHover={{ scale: config.scale * 1.1, filter: "brightness(1.2)" }}
        >
            {/* Walker Container - Flips based on direction */}
            <motion.div
                animate={{ scaleX: direction === 'right' ? 1 : -1 }}
                transition={{ duration: 0.4 }}
                className="relative w-full h-full flex items-center justify-center"
            >
                {videoSrc ? (
                    <video
                        src={videoSrc}
                        autoPlay
                        loop
                        muted
                        playsInline
                        className="w-full h-full object-contain drop-shadow-[0_4px_6px_rgba(0,0,0,0.3)]"
                    />
                ) : (
                    // Fallback "Spirit" if no video provided yet
                    <div className={cn("w-6 h-8 rounded-full opacity-90 relative", color)}>
                        {/* Body Glow */}
                        <div className={cn("absolute inset-0 blur-sm opacity-50", color)} />
                        {/* Head */}
                        <div className="w-2 h-2 bg-white/80 rounded-full absolute top-1 left-1/2 -translate-x-1/2" />
                        {/* Legs/Movement (Simple output for fallback) */}
                        <motion.div
                            className="absolute bottom-0 w-full h-2 bg-black/20"
                            animate={{ scaleY: [1, 0.8, 1] }}
                            transition={{ repeat: Infinity, duration: 0.5 }}
                        />
                    </div>
                )}

                {/* Reflection/Ground Shadow */}
                <div className={cn("absolute -bottom-2 w-8 h-1 rounded-[100%] bg-black/40 blur-sm transition-all group-hover:bg-cyan-500/30 group-hover:blur-md", direction === 'right' ? 'left-2' : 'right-2')} />
            </motion.div>
        </motion.div>
    )
}
