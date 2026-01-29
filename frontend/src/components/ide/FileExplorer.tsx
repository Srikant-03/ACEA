"use client"

import { Folder, FileCode, ChevronRight, ChevronDown } from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils"

interface FileExplorerProps {
    files: string[]
    onSelect: (path: string) => void
    selectedPath?: string
}

export function FileExplorer({ files, onSelect, selectedPath }: FileExplorerProps) {
    // Basic Flat List for MVP robustness
    // Todo: Implement true recursive tree for nested folders if needed

    // Sort files to group by folder roughly
    const sortedFiles = [...files].sort()

    return (
        <div className="h-full border-r border-slate-800 bg-slate-950 flex flex-col w-64">
            <div className="p-4 border-b border-slate-800 font-bold text-sm text-slate-400">
                EXPLORER
            </div>
            <div className="flex-1 overflow-y-auto p-2">
                {sortedFiles.map((path) => (
                    <div
                        key={path}
                        onClick={() => onSelect(path)}
                        className={cn(
                            "flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-sm mb-1 transition-colors",
                            selectedPath === path
                                ? "bg-blue-600/20 text-blue-400"
                                : "text-slate-400 hover:bg-slate-900 hover:text-white"
                        )}
                    >
                        <FileCode className="w-4 h-4 shrink-0" />
                        <span className="truncate">{path}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}
