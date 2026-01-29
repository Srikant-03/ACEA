"use client"

import Link from "next/link"
import { motion } from "framer-motion"
import { Activity, Terminal, Shield, Cpu } from "lucide-react"
import { Button } from "@/components/ui/button"

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col">
      <header className="border-b border-slate-800 p-4 flex items-center justify-between bg-slate-900/50 backdrop-blur">
        <div className="flex items-center gap-2">
          <Cpu className="text-blue-500" />
          <h1 className="text-xl font-bold tracking-tight">ACEA SENTINEL</h1>
        </div>
        <div className="flex gap-4">
          <Button variant="ghost" size="sm">Documentation</Button>
          <Button variant="outline" size="sm" className="border-slate-700">Settings</Button>
        </div>
      </header>

      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-slate-950">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <h1 className="text-6xl font-black mb-6 bg-gradient-to-r from-blue-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
            AUTONOMOUS SOFTWARE ENGINEERING
          </h1>
          <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-12">
            The world's first self-correcting AI platform that generates code, tests it in real browsers, and autonomously fixes bugs.
          </p>

          <div className="flex gap-6 justify-center">
            <Link href="/war-room">
              <Button size="lg" className="h-14 px-8 text-lg bg-blue-600 hover:bg-blue-500 shadow-[0_0_30px_rgba(37,99,235,0.3)] border-0">
                <Activity className="mr-2 w-5 h-5" />
                Enter War Room
              </Button>
            </Link>
            <Button size="lg" variant="outline" className="h-14 px-8 text-lg border-slate-700 hover:bg-slate-800 hover:text-white">
              <Terminal className="mr-2 w-5 h-5" />
              Open Terminal
            </Button>
          </div>
        </motion.div>

        <div className="mt-24 grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto text-left">
          <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/30 hover:border-blue-500/50 transition-colors">
            <Shield className="w-8 h-8 text-green-400 mb-4" />
            <h3 className="text-lg font-bold mb-2">Security First</h3>
            <p className="text-slate-400 text-sm">Every line of code is audited by Sentinel Agent against OWASP Top 10 vulnerabilities.</p>
          </div>
          <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/30 hover:border-purple-500/50 transition-colors">
            <Activity className="w-8 h-8 text-purple-400 mb-4" />
            <h3 className="text-lg font-bold mb-2">Self-Healing</h3>
            <p className="text-slate-400 text-sm">System autonomously detects bugs and applies fixes without human intervention.</p>
          </div>
          <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/30 hover:border-cyan-500/50 transition-colors">
            <Terminal className="w-8 h-8 text-cyan-400 mb-4" />
            <h3 className="text-lg font-bold mb-2">Live Execution</h3>
            <p className="text-slate-400 text-sm">Watch code being generated and executed in real-time with complete transparency.</p>
          </div>
        </div>
      </div>
    </main>
  )
}
