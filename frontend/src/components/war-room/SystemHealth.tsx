"use client"

import { motion } from "framer-motion"

export function SystemHealth() {
    return (
        <div className="bg-slate-900/50 border border-slate-800 p-4 rounded-lg">
            <h3 className="text-xs font-bold text-slate-500 mb-4 uppercase">System Vitality</h3>

            <div className="space-y-4">
                <div>
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-400">CPU Usage</span>
                        <span className="text-blue-400">42%</span>
                    </div>
                    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: "42%" }}
                            className="h-full bg-blue-500"
                        />
                    </div>
                </div>

                <div>
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-400">Memory Allocation</span>
                        <span className="text-purple-400">68%</span>
                    </div>
                    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: "68%" }}
                            className="h-full bg-purple-500"
                        />
                    </div>
                </div>

                <div>
                    <div className="flex justify-between text-xs mb-1">
                        <span className="text-slate-400">Neural Load</span>
                        <span className="text-green-400">Stable</span>
                    </div>
                    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: "90%" }}
                            className="h-full bg-green-500"
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}
