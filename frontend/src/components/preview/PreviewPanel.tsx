"use client"

import { useState, useRef, useCallback } from "react"
import { X, Maximize2, Minimize2, ExternalLink, Loader2, Cloud, RefreshCw, Monitor, Eye, ArrowLeft, ArrowRight, Home, Globe, Lock } from "lucide-react"

type PreviewMode = "preview" | "studio"

interface PreviewPanelProps {
    projectId?: string
    previewUrl?: string  // E2B sandbox URL for preview mode
    studioUrl?: string   // noVNC URL for studio mode
    techStack?: string
    mode?: PreviewMode
    onClose?: () => void
    isLoading?: boolean
    loadingStage?: string
    onTriggerVisualQA?: () => void
    visualQALoading?: boolean
    onModeSwitch?: (mode: PreviewMode) => void
}

export function PreviewPanel({
    projectId,
    previewUrl,
    studioUrl,
    techStack,
    mode = "preview",
    onClose,
    isLoading = false,
    loadingStage = "Creating sandbox...",
    onTriggerVisualQA,
    visualQALoading = false,
    onModeSwitch
}: PreviewPanelProps) {
    const [isFullscreen, setIsFullscreen] = useState(false)
    const [iframeKey, setIframeKey] = useState(0)
    const [urlHistory, setUrlHistory] = useState<string[]>([])
    const [historyIndex, setHistoryIndex] = useState(-1)
    const [displayPath, setDisplayPath] = useState("/")
    const iframeRef = useRef<HTMLIFrameElement>(null)

    const isStudioMode = mode === "studio"
    const activeUrl = isStudioMode ? studioUrl : previewUrl

    const panelClasses = isFullscreen
        ? "fixed inset-0 z-50 bg-slate-950"
        : "h-full w-full"

    // Generate semantic URL from raw E2B URL
    const getSemanticUrl = (rawUrl: string | undefined): string => {
        if (!rawUrl) return "/"
        // Hide the raw sandbox URL and show friendly path
        return displayPath
    }

    const handleRefresh = () => {
        setIframeKey(prev => prev + 1)
    }

    const handleBack = () => {
        if (historyIndex > 0) {
            setHistoryIndex(prev => prev - 1)
            // In real implementation, would navigate iframe
        }
    }

    const handleForward = () => {
        if (historyIndex < urlHistory.length - 1) {
            setHistoryIndex(prev => prev + 1)
        }
    }

    const handleHome = () => {
        setDisplayPath("/")
        handleRefresh()
    }

    // Handle iframe navigation (would need postMessage API in real impl)
    const handleIframeLoad = useCallback(() => {
        // Update history when iframe navigates
        if (activeUrl) {
            setUrlHistory(prev => {
                const newHistory = [...prev.slice(0, historyIndex + 1), displayPath]
                return newHistory
            })
            setHistoryIndex(prev => prev + 1)
        }
    }, [activeUrl, displayPath, historyIndex])

    return (
        <div className={panelClasses}>
            {/* Browser Chrome Header */}
            <div className="flex flex-col bg-slate-900 border-b border-slate-700">
                {/* Top bar with traffic lights and mode indicator */}
                <div className="flex items-center justify-between px-3 py-2">
                    <div className="flex items-center gap-2">
                        <div className="w-3 h-3 rounded-full bg-red-500 cursor-pointer hover:bg-red-400" onClick={onClose} />
                        <div className="w-3 h-3 rounded-full bg-yellow-500 cursor-pointer hover:bg-yellow-400" onClick={() => setIsFullscreen(false)} />
                        <div className="w-3 h-3 rounded-full bg-green-500 cursor-pointer hover:bg-green-400" onClick={() => setIsFullscreen(true)} />

                        {/* Mode Indicator Badge */}
                        <div className={`ml-3 flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${isStudioMode
                                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                                : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                            }`}>
                            {isStudioMode ? (
                                <>
                                    <Monitor className="w-3 h-3" />
                                    <span>Studio</span>
                                    <span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />
                                </>
                            ) : (
                                <>
                                    <Cloud className="w-3 h-3" />
                                    <span>Preview</span>
                                </>
                            )}
                        </div>

                        {/* Mode Switch Button */}
                        {onModeSwitch && (
                            <button
                                onClick={() => onModeSwitch(isStudioMode ? "preview" : "studio")}
                                className="ml-2 px-2 py-0.5 rounded text-xs bg-slate-700 hover:bg-slate-600 text-slate-300"
                            >
                                Switch to {isStudioMode ? "Preview" : "Studio"}
                            </button>
                        )}
                    </div>

                    <div className="flex items-center gap-2">
                        {/* Visual QA Button */}
                        {!isStudioMode && onTriggerVisualQA && activeUrl && !isLoading && (
                            <button
                                onClick={onTriggerVisualQA}
                                disabled={visualQALoading}
                                className="flex items-center gap-1 px-2 py-1 rounded bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30 text-xs disabled:opacity-50"
                                title="Run Visual QA with Gemini Vision"
                            >
                                {visualQALoading ? (
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                    <Eye className="w-3 h-3" />
                                )}
                                <span>Visual QA</span>
                            </button>
                        )}

                        <button
                            onClick={() => setIsFullscreen(!isFullscreen)}
                            className="text-slate-400 hover:text-white p-1"
                            title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
                        >
                            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                        </button>
                        {onClose && (
                            <button
                                onClick={onClose}
                                className="text-slate-400 hover:text-white p-1"
                                title="Close preview"
                            >
                                <X className="w-4 h-4" />
                            </button>
                        )}
                    </div>
                </div>

                {/* URL Bar */}
                {!isStudioMode && activeUrl && !isLoading && (
                    <div className="flex items-center gap-2 px-3 py-1.5 border-t border-slate-800">
                        {/* Navigation buttons */}
                        <div className="flex items-center gap-1">
                            <button
                                onClick={handleBack}
                                disabled={historyIndex <= 0}
                                className="p-1 rounded hover:bg-slate-700 text-slate-400 disabled:opacity-30"
                            >
                                <ArrowLeft className="w-4 h-4" />
                            </button>
                            <button
                                onClick={handleForward}
                                disabled={historyIndex >= urlHistory.length - 1}
                                className="p-1 rounded hover:bg-slate-700 text-slate-400 disabled:opacity-30"
                            >
                                <ArrowRight className="w-4 h-4" />
                            </button>
                            <button
                                onClick={handleRefresh}
                                className="p-1 rounded hover:bg-slate-700 text-slate-400"
                            >
                                <RefreshCw className="w-4 h-4" />
                            </button>
                            <button
                                onClick={handleHome}
                                className="p-1 rounded hover:bg-slate-700 text-slate-400"
                            >
                                <Home className="w-4 h-4" />
                            </button>
                        </div>

                        {/* Semantic URL Bar */}
                        <div className="flex-1 flex items-center gap-2 bg-slate-800 rounded-lg px-3 py-1.5">
                            <Lock className="w-3 h-3 text-green-500" />
                            <span className="text-slate-500 text-sm">preview/</span>
                            <span className="text-slate-300 text-sm font-medium">
                                {projectId || 'project'}
                            </span>
                            <span className="text-slate-400 text-sm">{displayPath}</span>
                        </div>

                        {/* External link */}
                        <a
                            href={activeUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1 rounded hover:bg-slate-700 text-slate-400"
                            title="Open in new tab"
                        >
                            <ExternalLink className="w-4 h-4" />
                        </a>
                    </div>
                )}
            </div>

            {/* Preview Content */}
            <div className={`${isFullscreen ? 'h-[calc(100vh-88px)]' : 'h-[calc(100%-88px)]'} bg-slate-900`}>
                {isLoading ? (
                    <div className="flex flex-col items-center justify-center h-full text-white">
                        <div className="relative">
                            <div className={`absolute inset-0 ${isStudioMode ? 'bg-purple-500/20' : 'bg-blue-500/20'} rounded-full blur-xl animate-pulse`} />
                            <Loader2 className={`w-16 h-16 animate-spin ${isStudioMode ? 'text-purple-500' : 'text-blue-500'} relative z-10`} />
                        </div>
                        <p className="text-xl font-semibold mt-6">{loadingStage}</p>
                        <p className="text-slate-400 text-sm mt-2">
                            {isStudioMode
                                ? "Starting full desktop environment..."
                                : "This may take a few seconds"
                            }
                        </p>
                        <div className="mt-6 flex gap-2">
                            <div className={`w-2 h-2 rounded-full ${isStudioMode ? 'bg-purple-500' : 'bg-blue-500'} animate-bounce`} style={{ animationDelay: '0ms' }} />
                            <div className={`w-2 h-2 rounded-full ${isStudioMode ? 'bg-purple-500' : 'bg-blue-500'} animate-bounce`} style={{ animationDelay: '150ms' }} />
                            <div className={`w-2 h-2 rounded-full ${isStudioMode ? 'bg-purple-500' : 'bg-blue-500'} animate-bounce`} style={{ animationDelay: '300ms' }} />
                        </div>
                    </div>
                ) : activeUrl ? (
                    <iframe
                        ref={iframeRef}
                        key={iframeKey}
                        src={activeUrl}
                        className="w-full h-full border-0 bg-white"
                        title={isStudioMode ? "Studio Mode Desktop" : "E2B Cloud Preview"}
                        allow="accelerometer; camera; encrypted-media; geolocation; gyroscope; microphone; midi; clipboard-read; clipboard-write"
                        onLoad={handleIframeLoad}
                    />
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-500">
                        {isStudioMode ? (
                            <>
                                <Monitor className="w-12 h-12 mb-4 text-purple-600/50" />
                                <p>Studio Mode not active</p>
                                <p className="text-sm mt-1">Click "Studio" to start a desktop environment</p>
                            </>
                        ) : (
                            <>
                                <Globe className="w-12 h-12 mb-4 text-slate-600" />
                                <p>No preview available</p>
                                <p className="text-sm mt-1">Click RUN to start the project</p>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}
