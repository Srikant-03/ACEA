"use client"

import { motion } from "framer-motion"

export function NetworkMap() {
    return (
        <div className="h-48 relative border border-slate-800 bg-slate-950/50 rounded-lg overflow-hidden flex items-center justify-center">
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900/20 via-slate-900/0 to-slate-950/0"></div>

            {/* Simplified Grid Globe */}
            <div className="relative w-32 h-32 rounded-full border border-slate-700/50 flex items-center justify-center">
                <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-0 rounded-full border border-dashed border-slate-600/30"
                />
                <div className="w-2 h-2 bg-blue-500 rounded-full shadow-[0_0_10px_rgba(59,130,246,0.8)]" />

                {/* Ping animation */}
                <motion.div
                    initial={{ scale: 1, opacity: 0.8 }}
                    animate={{ scale: 3, opacity: 0 }}
                    transition={{ duration: 2, repeat: Infinity }}
                    className="absolute w-2 h-2 bg-blue-500 rounded-full"
                />
            </div>

            <div className="absolute bottom-2 right-2 text-[10px] text-slate-500 font-mono">
                UPLINK: ACTIVE
            </div>
        </div>
    )
}
