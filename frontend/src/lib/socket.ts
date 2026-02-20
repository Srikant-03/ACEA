"use client"

import { io } from "socket.io-client"

// Connect to the backend URL
export const socket = io(process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000", {
    transports: ["websocket"],
    autoConnect: true,
})
