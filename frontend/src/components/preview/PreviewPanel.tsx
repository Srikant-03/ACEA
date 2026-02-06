"use client"

import { useState } from "react"
import { X, Maximize2, Minimize2, ExternalLink, Loader2, Cloud, RefreshCw } from "lucide-react"

interface PreviewPanelProps {
    previewUrl?: string  // E2B sandbox URL
    techStack?: string
    onClose?: () => void
    isLoading?: boolean
    loadingStage?: string  // "Creating sandbox...", "Installing dependencies...", etc.
}

export function PreviewPanel({
    previewUrl,
    techStack,
    onClose,
    isLoading = false,
    loadingStage = "Creating sandbox..."
}: PreviewPanelProps) {
    const [isFullscreen, setIsFullscreen] = useState(false)
    const [iframeKey, setIframeKey] = useState(0)

    const panelClasses = isFullscreen
        ? "fixed inset-0 z-50 bg-slate-950"
        : "h-full w-full"

    const handleRefresh = () => {
        setIframeKey(prev => prev + 1)
    }

    return (
        <div className={panelClasses}>
            {/* Header */}
            <div className="flex items-center justify-between bg-slate-900 border-b border-slate-700 px-3 py-2">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full bg-red-500" />
                    <div className="w-3 h-3 rounded-full bg-yellow-500" />
                    <div className="w-3 h-3 rounded-full bg-green-500" />
                    <Cloud className="w-4 h-4 text-blue-400 ml-2" />
                    <span className="text-slate-400 text-xs">
                        E2B Cloud Preview
                        {techStack && <span className="text-slate-500"> • {techStack}</span>}
                    </span>
                    {previewUrl && !isLoading && (
                        <>
                            <button
                                onClick={handleRefresh}
                                className="text-slate-400 hover:text-white p-1 ml-2"
                                title="Refresh preview"
                            >
                                <RefreshCw className="w-3 h-3" />
                            </button>
                            <a
                                href={previewUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-400 hover:text-blue-300 text-xs flex items-center gap-1"
                                title="Open in new tab"
                            >
                                <ExternalLink className="w-3 h-3" />
                                <span className="hidden sm:inline truncate max-w-[200px]">{previewUrl}</span>
                            </a>
                        </>
                    )}
                </div>
                <div className="flex items-center gap-2">
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

            {/* Preview Content */}
            <div className={`${isFullscreen ? 'h-[calc(100vh-44px)]' : 'h-[calc(100%-44px)]'} bg-slate-900`}>
                {isLoading ? (
                    <div className="flex flex-col items-center justify-center h-full text-white">
                        <div className="relative">
                            <div className="absolute inset-0 bg-blue-500/20 rounded-full blur-xl animate-pulse" />
                            <Loader2 className="w-16 h-16 animate-spin text-blue-500 relative z-10" />
                        </div>
                        <p className="text-xl font-semibold mt-6">{loadingStage}</p>
                        <p className="text-slate-400 text-sm mt-2">This may take a few seconds</p>
                        <div className="mt-6 flex gap-2">
                            <div className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '0ms' }} />
                            <div className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '150ms' }} />
                            <div className="w-2 h-2 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                    </div>
                ) : previewUrl ? (
                    <iframe
                        key={iframeKey}
                        src={previewUrl}
                        className="w-full h-full border-0 bg-white"
                        title="E2B Cloud Preview"
                        allow="accelerometer; camera; encrypted-media; geolocation; gyroscope; microphone; midi"
                    />
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-500">
                        <Cloud className="w-12 h-12 mb-4 text-slate-600" />
                        <p>No preview available</p>
                        <p className="text-sm mt-1">Click RUN to start the project</p>
                    </div>
                )}
            </div>
        </div>
    )
}
