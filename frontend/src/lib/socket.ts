"use client"

import { io } from "socket.io-client"

// Connect to the backend URL
export const socket = io("http://localhost:8000", {
    transports: ["websocket"],
    autoConnect: true,
})
