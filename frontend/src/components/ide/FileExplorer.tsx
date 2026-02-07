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
        <div className="h-full flex flex-col w-full bg-transparent">
            {/* Header removed to avoid duplication with parent container */}
            <div className="flex-1 overflow-y-auto p-2">
                {sortedFiles.map((path) => (
                    <div
                        key={path}
                        onClick={() => onSelect(path)}
                        className={cn(
                            "flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-[11px] font-mono mb-1 transition-all",
                            selectedPath === path
                                ? "bg-white/10 text-zinc-100 font-bold border border-white/5"
                                : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
                        )}
                    >
                        <FileCode className={cn("w-3 h-3 shrink-0", selectedPath === path ? "text-zinc-100" : "text-zinc-600")} />
                        <span className="truncate">{path}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}
