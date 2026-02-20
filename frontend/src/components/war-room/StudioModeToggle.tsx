"use client"

import { useState } from "react"
import { Monitor, Play, Pause, Clock, AlertTriangle, Loader2 } from "lucide-react"

interface StudioModeToggleProps {
    projectId: string
    isActive: boolean
    timeRemaining?: number  // minutes
    onActivate: () => Promise<void>
    onDeactivate: () => Promise<void>
    onExtend?: (minutes: number) => Promise<void>
}

export function StudioModeToggle({
    projectId,
    isActive,
    timeRemaining = 0,
    onActivate,
    onDeactivate,
    onExtend
}: StudioModeToggleProps) {
    const [isLoading, setIsLoading] = useState(false)
    const [showConfirmDialog, setShowConfirmDialog] = useState(false)
    const [showExtendDialog, setShowExtendDialog] = useState(false)

    const handleToggle = async () => {
        if (isActive) {
            // Deactivate immediately
            setIsLoading(true)
            try {
                await onDeactivate()
            } finally {
                setIsLoading(false)
            }
        } else {
            // Show confirmation before activating
            setShowConfirmDialog(true)
        }
    }

    const handleConfirmActivate = async () => {
        setShowConfirmDialog(false)
        setIsLoading(true)
        try {
            await onActivate()
        } finally {
            setIsLoading(false)
        }
    }

    const handleExtend = async (minutes: number) => {
        if (onExtend) {
            setIsLoading(true)
            try {
                await onExtend(minutes)
            } finally {
                setIsLoading(false)
                setShowExtendDialog(false)
            }
        }
    }

    const formatTime = (minutes: number) => {
        const hrs = Math.floor(minutes / 60)
        const mins = minutes % 60
        if (hrs > 0) {
            return `${hrs}h ${mins}m`
        }
        return `${mins}m`
    }

    // Warning when less than 10 minutes remaining
    const isLowTime = isActive && timeRemaining < 10

    return (
        <>
            {/* Main Toggle Button */}
            <div className="flex items-center gap-2">
                {isActive && (
                    <div className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs ${isLowTime
                            ? "bg-amber-500/20 text-amber-400"
                            : "bg-slate-700/50 text-slate-400"
                        }`}>
                        <Clock className="w-3 h-3" />
                        <span>{formatTime(timeRemaining)}</span>
                        {isLowTime && (
                            <AlertTriangle className="w-3 h-3 text-amber-400" />
                        )}
                    </div>
                )}

                <button
                    onClick={handleToggle}
                    disabled={isLoading}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${isActive
                            ? "bg-purple-600 hover:bg-purple-700 text-white"
                            : "bg-slate-700 hover:bg-slate-600 text-slate-300"
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                    title={isActive ? "Exit Studio Mode" : "Enter Studio Mode"}
                >
                    {isLoading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Monitor className="w-4 h-4" />
                    )}
                    <span>{isActive ? "Studio Mode" : "Studio"}</span>
                    {isActive && (
                        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                    )}
                </button>

                {isActive && onExtend && (
                    <button
                        onClick={() => setShowExtendDialog(true)}
                        className="px-2 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 text-xs"
                        title="Extend session"
                    >
                        +30m
                    </button>
                )}
            </div>

            {/* Activation Confirmation Dialog */}
            {showConfirmDialog && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
                    <div className="bg-slate-800 rounded-xl p-6 max-w-md mx-4 border border-slate-700 shadow-2xl">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 rounded-lg bg-purple-500/20">
                                <Monitor className="w-6 h-6 text-purple-400" />
                            </div>
                            <h3 className="text-lg font-semibold text-white">
                                Activate Studio Mode
                            </h3>
                        </div>

                        <p className="text-slate-300 mb-4">
                            Studio Mode provides a full desktop environment with VS Code and Chrome
                            for hands-on development.
                        </p>

                        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 mb-4">
                            <div className="flex items-start gap-2">
                                <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                                <div className="text-sm">
                                    <p className="text-amber-400 font-medium">Cost Warning</p>
                                    <p className="text-amber-300/80">
                                        Desktop VMs are more expensive than standard preview mode.
                                        Sessions are time-limited and will auto-suspend when idle.
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={() => setShowConfirmDialog(false)}
                                className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleConfirmActivate}
                                className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white font-medium flex items-center gap-2"
                            >
                                <Play className="w-4 h-4" />
                                Activate Studio Mode
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Extend Session Dialog */}
            {showExtendDialog && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
                    <div className="bg-slate-800 rounded-xl p-6 max-w-sm mx-4 border border-slate-700 shadow-2xl">
                        <h3 className="text-lg font-semibold text-white mb-4">
                            Extend Session
                        </h3>

                        <p className="text-slate-400 text-sm mb-4">
                            Current time remaining: {formatTime(timeRemaining)}
                        </p>

                        <div className="flex flex-col gap-2">
                            {[15, 30, 60].map((mins) => (
                                <button
                                    key={mins}
                                    onClick={() => handleExtend(mins)}
                                    disabled={isLoading}
                                    className="w-full px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300 disabled:opacity-50"
                                >
                                    +{mins} minutes
                                </button>
                            ))}
                        </div>

                        <button
                            onClick={() => setShowExtendDialog(false)}
                            className="w-full mt-3 px-4 py-2 rounded-lg bg-slate-600 hover:bg-slate-500 text-slate-300"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            )}
        </>
    )
}
