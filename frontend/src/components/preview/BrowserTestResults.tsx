"use client"

import { useState } from "react"
import {
    X, ChevronDown, ChevronRight, AlertTriangle, CheckCircle2,
    XCircle, Eye, Gauge, Accessibility, Smartphone, Search, Send,
    Loader2, Link, FileText, MousePointerClick
} from "lucide-react"

interface BrowserTestResultsProps {
    results: BrowserTestReport | null
    isRunning: boolean
    progress?: TestProgress | null
    onClose: () => void
    onSendToFix?: (errors: string[]) => void
}

export interface TestProgress {
    phase: string
    message: string
    url?: string
    overall_status?: string
    validation_level?: string
}

export interface BrowserTestReport {
    project_id: string
    url?: string
    validation_level?: string
    overall_status: string
    scores: Record<string, number | null>
    categories: Record<string, string[]>
    total_issues: number
    tests: Record<string, TestResult>
    duration_ms?: number
    timestamp?: string
    error?: string
}

interface TestResult {
    status: string
    issues: string[]
    [key: string]: any
}

const CATEGORY_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
    interactive: { icon: <Eye className="w-3.5 h-3.5" />, label: "Interactivity", color: "cyan" },
    accessibility: { icon: <Accessibility className="w-3.5 h-3.5" />, label: "Accessibility", color: "violet" },
    responsive: { icon: <Smartphone className="w-3.5 h-3.5" />, label: "Responsiveness", color: "blue" },
    performance: { icon: <Gauge className="w-3.5 h-3.5" />, label: "Performance", color: "amber" },
    seo: { icon: <Search className="w-3.5 h-3.5" />, label: "SEO", color: "emerald" },
    links: { icon: <Eye className="w-3.5 h-3.5" />, label: "Links", color: "sky" },
    forms: { icon: <Eye className="w-3.5 h-3.5" />, label: "Forms", color: "rose" },
    console: { icon: <AlertTriangle className="w-3.5 h-3.5" />, label: "Console Errors", color: "amber" },
    network: { icon: <XCircle className="w-3.5 h-3.5" />, label: "Network Failures", color: "red" },
    visual_overlap: { icon: <Eye className="w-3.5 h-3.5" />, label: "Visual Overlap", color: "indigo" },
    prompt_alignment: { icon: <FileText className="w-3.5 h-3.5" />, label: "Prompt Alignment", color: "purple" },
    feature_interaction: { icon: <MousePointerClick className="w-3.5 h-3.5" />, label: "Feature Interaction", color: "pink" },
    contrast_check: { icon: <Eye className="w-3.5 h-3.5" />, label: "Contrast Check", color: "orange" },
}

function ScoreGauge({ score, size = 40 }: { score: number | null; size?: number }) {
    if (score === null || score === undefined) return (
        <span className="text-xs text-slate-500">N/A</span>
    )
    const radius = (size - 6) / 2
    const circumference = 2 * Math.PI * radius
    const offset = circumference - (score / 100) * circumference
    const color = score >= 90 ? "#22c55e" : score >= 70 ? "#eab308" : score >= 50 ? "#f97316" : "#ef4444"

    return (
        <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
            <svg width={size} height={size} className="-rotate-90">
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#1e293b" strokeWidth={3} />
                <circle
                    cx={size / 2} cy={size / 2} r={radius} fill="none"
                    stroke={color} strokeWidth={3}
                    strokeDasharray={circumference} strokeDashoffset={offset}
                    strokeLinecap="round"
                    className="transition-all duration-700"
                />
            </svg>
            <span className="absolute text-[10px] font-bold" style={{ color }}>{score}</span>
        </div>
    )
}

function StatusBadge({ status }: { status: string }) {
    const map: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
        EXCELLENT: { bg: "bg-emerald-500/20", text: "text-emerald-400", icon: <CheckCircle2 className="w-3 h-3" /> },
        GOOD: { bg: "bg-green-500/20", text: "text-green-400", icon: <CheckCircle2 className="w-3 h-3" /> },
        PASS: { bg: "bg-green-500/20", text: "text-green-400", icon: <CheckCircle2 className="w-3 h-3" /> },
        FAIR: { bg: "bg-yellow-500/20", text: "text-yellow-400", icon: <AlertTriangle className="w-3 h-3" /> },
        WARN: { bg: "bg-yellow-500/20", text: "text-yellow-400", icon: <AlertTriangle className="w-3 h-3" /> },
        POOR: { bg: "bg-red-500/20", text: "text-red-400", icon: <XCircle className="w-3 h-3" /> },
        FAIL: { bg: "bg-red-500/20", text: "text-red-400", icon: <XCircle className="w-3 h-3" /> },
        ERROR: { bg: "bg-red-500/20", text: "text-red-400", icon: <XCircle className="w-3 h-3" /> },
        SKIPPED: { bg: "bg-slate-500/20", text: "text-slate-400", icon: null },
    }
    const s = map[status] || map.SKIPPED!
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${s.bg} ${s.text}`}>
            {s.icon} {status}
        </span>
    )
}

export function BrowserTestResults({
    results,
    isRunning,
    progress,
    onClose,
    onSendToFix,
}: BrowserTestResultsProps) {
    const [expandedTests, setExpandedTests] = useState<Set<string>>(new Set())

    const toggleTest = (name: string) => {
        setExpandedTests(prev => {
            const next = new Set(prev)
            if (next.has(name)) next.delete(name)
            else next.add(name)
            return next
        })
    }

    // Collect all issues for "Send to Fix"
    const allIssues: string[] = results
        ? Object.values(results.categories || {}).flat()
        : []

    return (
        <div className="absolute bottom-0 left-0 right-0 z-30 max-h-[55%] bg-slate-950/95 backdrop-blur-md border-t border-slate-700 overflow-hidden flex flex-col animate-in slide-in-from-bottom duration-300">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800 shrink-0">
                <div className="flex items-center gap-3">
                    <span className="text-xs font-bold text-white tracking-wider uppercase">Browser Test</span>
                    {isRunning && (
                        <span className="flex items-center gap-1.5 text-xs text-cyan-400">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            {progress?.message || "Running…"}
                        </span>
                    )}
                    {results && !isRunning && (
                        <>
                            <StatusBadge status={results.overall_status} />
                            {results.duration_ms && (
                                <span className="text-[10px] text-slate-500">
                                    {(results.duration_ms / 1000).toFixed(1)}s
                                </span>
                            )}
                            {results.total_issues > 0 && (
                                <span className="text-[10px] text-red-400">
                                    {results.total_issues} issue{results.total_issues !== 1 ? "s" : ""}
                                </span>
                            )}
                        </>
                    )}
                </div>

                <div className="flex items-center gap-2">
                    {/* Send to Fix */}
                    {onSendToFix && allIssues.length > 0 && !isRunning && (
                        <button
                            onClick={() => onSendToFix(allIssues)}
                            className="flex items-center gap-1 px-2 py-1 rounded bg-amber-600/20 text-amber-400 hover:bg-amber-600/30 text-xs font-medium transition-colors"
                            title="Feed errors into self-healing pipeline"
                        >
                            <Send className="w-3 h-3" />
                            Send to Fix
                        </button>
                    )}

                    <button onClick={onClose} className="p-1 text-slate-400 hover:text-white">
                        <X className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {results?.error && (
                    <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                        {results.error}
                    </div>
                )}

                {/* Score Overview */}
                {results?.scores && Object.keys(results.scores).length > 0 && (
                    <div className="flex items-center gap-4 pb-2 border-b border-slate-800">
                        <ScoreGauge score={results.scores.overall ?? null} size={48} />
                        <div className="flex flex-wrap gap-3">
                            {Object.entries(results.scores)
                                .filter(([k]) => k !== "overall")
                                .map(([key, val]) => {
                                    const meta = CATEGORY_META[key]
                                    return (
                                        <div key={key} className="flex items-center gap-1.5">
                                            <ScoreGauge score={val} size={32} />
                                            <span className="text-[10px] text-slate-400">{meta?.label || key}</span>
                                        </div>
                                    )
                                })}
                        </div>
                    </div>
                )}

                {/* Per-test expandable cards */}
                {results?.tests && Object.entries(results.tests).map(([testName, testResult]) => {
                    const meta = CATEGORY_META[testName]
                    const isExpanded = expandedTests.has(testName)
                    const issues = testResult.issues || []

                    return (
                        <div key={testName} className="rounded-lg border border-slate-800 overflow-hidden">
                            <button
                                onClick={() => toggleTest(testName)}
                                className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-800/50 transition-colors"
                            >
                                <div className="flex items-center gap-2">
                                    <span className={`text-${meta?.color || "slate"}-400`}>
                                        {meta?.icon || <Eye className="w-3.5 h-3.5" />}
                                    </span>
                                    <span className="text-xs font-medium text-slate-200">
                                        {meta?.label || testName}
                                    </span>
                                    <StatusBadge status={testResult.status} />
                                    {issues.length > 0 && (
                                        <span className="text-[10px] text-slate-500">
                                            {issues.length} issue{issues.length !== 1 ? "s" : ""}
                                        </span>
                                    )}
                                </div>
                                {isExpanded
                                    ? <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
                                    : <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                                }
                            </button>

                            {isExpanded && issues.length > 0 && (
                                <div className="px-3 pb-2 space-y-1">
                                    {issues.map((issue, i) => (
                                        <div
                                            key={i}
                                            className="flex items-start gap-2 px-2 py-1.5 rounded bg-slate-900/50 text-[11px] text-slate-300"
                                        >
                                            <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0 mt-0.5" />
                                            <span>{issue}</span>
                                        </div>
                                    ))}
                                </div>
                            )}

                            {isExpanded && testName === "feature_interaction" && testResult.interaction_log && (
                                <div className="px-3 pb-2 space-y-1 border-t border-slate-800/50 pt-2 mt-2">
                                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Interaction Log</p>
                                    {testResult.interaction_log.map((log: string, k: number) => (
                                        <div key={k} className="text-[11px] text-slate-400 font-mono">
                                            {log}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {isExpanded && issues.length === 0 && !testResult.interaction_log && (
                                <div className="px-3 pb-2">
                                    <span className="text-[11px] text-emerald-500">✓ No issues detected</span>
                                </div>
                            )}
                        </div>
                    )
                })}

                {/* Running placeholder */}
                {isRunning && !results && (
                    <div className="flex flex-col items-center justify-center py-8 text-center">
                        <Loader2 className="w-8 h-8 text-cyan-500 animate-spin mb-3" />
                        <p className="text-xs text-slate-400">{progress?.message || "Initializing browser tests…"}</p>
                    </div>
                )}
            </div>
        </div>
    )
}
