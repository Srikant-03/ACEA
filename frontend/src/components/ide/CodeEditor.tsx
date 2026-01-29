"use client"

import Editor from "@monaco-editor/react"

interface CodeEditorProps {
    code: string
    language?: string
    readOnly?: boolean
}

export function CodeEditor({ code, language = "python", readOnly = true }: CodeEditorProps) {
    return (
        <div className="h-full w-full border border-slate-800 rounded-md overflow-hidden bg-[#1e1e1e]">
            <Editor
                height="100%"
                defaultLanguage={language}
                value={code}
                theme="vs-dark"
                options={{
                    readOnly: readOnly,
                    minimap: { enabled: false },
                    fontSize: 14,
                    scrollBeyondLastLine: false,
                    automaticLayout: true
                }}
            />
        </div>
    )
}
