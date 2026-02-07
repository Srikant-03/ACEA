"use client"

import Link from "next/link"
import dynamic from 'next/dynamic';
import { motion } from "framer-motion"
import { Activity, Terminal, Shield, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"

const Spline = dynamic(() => import('@splinetool/react-spline'), {
  ssr: false,
  loading: () => <div className="w-full h-full bg-slate-950 animate-pulse" />,
});

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex flex-col relative overflow-hidden font-sans">
      {/* Background Spline Layer - Full Screen */}
      <div className="fixed inset-0 z-0 scale-150 pt-20">
        <Spline
          scene="https://prod.spline.design/9aAmTJ1E85P0eEl6/scene.splinecode"
          className="w-full h-full"
        />
      </div>

      {/* Content Overlay - Pointer Events None to allow click-through to Spline where empty */}
      <div className="relative z-10 flex flex-col min-h-screen pointer-events-none">


        {/* Main Content Area */}
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          <motion.div
            initial={{ y: 20, opacity: 1 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.8 }}
            className="pointer-events-auto max-w-4xl mx-auto"
          >
            <h1 className="text-7xl md:text-8xl text-slate-300 tracking-tight mb-2 font-orbitron font-bold [text-shadow:1px_0_0_rgba(203,213,225,0.4),-1px_0_0_rgba(203,213,225,0.4),0_1px_0_rgba(203,213,225,0.4),0_-1px_0_rgba(203,213,225,0.4)] drop-shadow-[0_0_15px_rgba(255,255,255,0.1)]">
              ACEA
            </h1>


            <p className="text-2xl md:text-3xl text-slate-400 max-w-2xl mx-auto mb-12 font-orbitron tracking-wide leading-relaxed drop-shadow-md">
              Code that debugs itself
            </p>

            <div className="flex gap-6 justify-center">
              <Link href="/war-room">
                <Button size="lg" className="h-12 px-8 text-sm font-bold tracking-widest bg-slate-800/80 hover:bg-slate-700 text-slate-200 shadow-[0_0_20px_rgba(255,255,255,0.1)] border border-slate-600/30 rounded-full transition-all hover:scale-105 font-orbitron uppercase backdrop-blur-sm">
                  Initialize
                </Button>
              </Link>
            </div>
          </motion.div>
        </div>



      </div>
    </main>
  )
}