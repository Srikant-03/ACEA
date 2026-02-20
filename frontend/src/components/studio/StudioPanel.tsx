'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';

interface StudioPanelProps {
    projectId: string;
    novncUrl: string | null;
    onExit?: () => void;
    onSync?: () => void;
}

interface SessionInfo {
    time_remaining_minutes: number;
    session_status: string;
    vscode_status: string;
    chrome_status: string;
}

export default function StudioPanel({
    projectId,
    novncUrl,
    onExit,
    onSync
}: StudioPanelProps) {
    const iframeRef = useRef<HTMLIFrameElement>(null);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
    const [isSyncing, setIsSyncing] = useState(false);
    const [showExitConfirm, setShowExitConfirm] = useState(false);

    // Heartbeat to keep session alive
    useEffect(() => {
        if (!projectId || !novncUrl) return;

        const sendHeartbeat = async () => {
            try {
                const res = await fetch(`/api/studio/${projectId}/heartbeat`, {
                    method: 'POST'
                });
                if (res.ok) {
                    const data = await res.json();
                    setSessionInfo({
                        time_remaining_minutes: data.time_remaining_minutes,
                        session_status: data.session_status,
                        vscode_status: 'ready',
                        chrome_status: 'ready'
                    });
                }
            } catch (error) {
                console.error('Heartbeat failed:', error);
            }
        };

        // Initial heartbeat
        sendHeartbeat();

        // Heartbeat every 5 minutes
        const interval = setInterval(sendHeartbeat, 5 * 60 * 1000);

        return () => clearInterval(interval);
    }, [projectId, novncUrl]);

    // Handle fullscreen toggle
    const toggleFullscreen = useCallback(() => {
        if (!iframeRef.current) return;

        if (!isFullscreen) {
            if (iframeRef.current.requestFullscreen) {
                iframeRef.current.requestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
        setIsFullscreen(!isFullscreen);
    }, [isFullscreen]);

    // Handle file sync
    const handleSync = async () => {
        setIsSyncing(true);
        try {
            const res = await fetch(`/api/studio/${projectId}/sync`, {
                method: 'POST'
            });
            if (res.ok) {
                const data = await res.json();
                console.log(`Synced ${data.files_count} files from Studio`);
                onSync?.();
            }
        } catch (error) {
            console.error('Sync failed:', error);
        } finally {
            setIsSyncing(false);
        }
    };

    // Handle session extension
    const handleExtend = async () => {
        try {
            const res = await fetch(`/api/studio/${projectId}/extend`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ timeout_minutes: 30 })
            });
            if (res.ok) {
                const data = await res.json();
                setSessionInfo(prev => prev ? {
                    ...prev,
                    time_remaining_minutes: data.time_remaining_minutes
                } : null);
            }
        } catch (error) {
            console.error('Extend failed:', error);
        }
    };

    // Handle exit with confirmation
    const handleExit = () => {
        setShowExitConfirm(true);
    };

    const confirmExit = async () => {
        // Sync files before exiting
        await handleSync();

        // Deactivate studio mode
        try {
            await fetch(`/api/studio/${projectId}`, {
                method: 'DELETE'
            });
            onExit?.();
        } catch (error) {
            console.error('Exit failed:', error);
        }
        setShowExitConfirm(false);
    };

    // Format time remaining
    const formatTime = (minutes: number) => {
        if (minutes >= 60) {
            const hours = Math.floor(minutes / 60);
            const mins = minutes % 60;
            return `${hours}h ${mins}m`;
        }
        return `${minutes}m`;
    };

    // Time warning color
    const getTimeColor = (minutes: number) => {
        if (minutes <= 5) return 'text-red-500';
        if (minutes <= 15) return 'text-yellow-500';
        return 'text-green-500';
    };

    if (!novncUrl) {
        return (
            <div className="studio-panel-container" style={styles.container}>
                <div style={styles.loading}>
                    <div style={styles.spinner} />
                    <p>Starting Studio Mode...</p>
                    <p style={styles.subtext}>Setting up VS Code and Chrome</p>
                </div>
            </div>
        );
    }

    return (
        <div className="studio-panel-container" style={styles.container}>
            {/* Toolbar */}
            <div style={styles.toolbar}>
                <div style={styles.toolbarLeft}>
                    <span style={styles.modeIndicator}>
                        <span style={styles.modeDot} />
                        Studio Mode
                    </span>

                    {sessionInfo && (
                        <span className={getTimeColor(sessionInfo.time_remaining_minutes)} style={styles.timeRemaining}>
                            ⏱️ {formatTime(sessionInfo.time_remaining_minutes)}
                        </span>
                    )}
                </div>

                <div style={styles.toolbarRight}>
                    <button
                        onClick={handleSync}
                        style={styles.button}
                        disabled={isSyncing}
                        title="Sync files to backend"
                    >
                        {isSyncing ? '⏳' : '🔄'} Sync
                    </button>

                    <button
                        onClick={handleExtend}
                        style={styles.button}
                        title="Extend session by 30 minutes"
                    >
                        ➕ Extend
                    </button>

                    <button
                        onClick={toggleFullscreen}
                        style={styles.button}
                        title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
                    >
                        {isFullscreen ? '⬜' : '⛶'}
                    </button>

                    <button
                        onClick={handleExit}
                        style={{ ...styles.button, ...styles.exitButton }}
                        title="Exit Studio Mode"
                    >
                        ✕ Exit
                    </button>
                </div>
            </div>

            {/* noVNC iframe */}
            <iframe
                ref={iframeRef}
                src={novncUrl}
                style={styles.iframe}
                title="Studio Desktop"
                allow="fullscreen; clipboard-read; clipboard-write"
                sandbox="allow-same-origin allow-scripts allow-popups allow-forms allow-modals"
            />

            {/* Exit confirmation modal */}
            {showExitConfirm && (
                <div style={styles.modal}>
                    <div style={styles.modalContent}>
                        <h3 style={styles.modalTitle}>Exit Studio Mode?</h3>
                        <p style={styles.modalText}>
                            Your files will be synced before exiting.
                            The desktop environment will be terminated.
                        </p>
                        <div style={styles.modalButtons}>
                            <button
                                onClick={() => setShowExitConfirm(false)}
                                style={styles.cancelButton}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={confirmExit}
                                style={styles.confirmButton}
                            >
                                Sync & Exit
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

const styles: { [key: string]: React.CSSProperties } = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#1e1e1e',
        borderRadius: '8px',
        overflow: 'hidden',
    },
    toolbar: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 12px',
        backgroundColor: '#2d2d2d',
        borderBottom: '1px solid #404040',
    },
    toolbarLeft: {
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
    },
    toolbarRight: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
    },
    modeIndicator: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        color: '#a78bfa',
        fontWeight: 600,
        fontSize: '14px',
    },
    modeDot: {
        width: '8px',
        height: '8px',
        borderRadius: '50%',
        backgroundColor: '#a78bfa',
        boxShadow: '0 0 8px #a78bfa',
    },
    timeRemaining: {
        fontSize: '13px',
        fontFamily: 'monospace',
    },
    button: {
        padding: '6px 12px',
        backgroundColor: '#404040',
        border: 'none',
        borderRadius: '4px',
        color: '#e0e0e0',
        cursor: 'pointer',
        fontSize: '13px',
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        transition: 'background-color 0.2s',
    },
    exitButton: {
        backgroundColor: '#dc2626',
    },
    iframe: {
        flex: 1,
        width: '100%',
        border: 'none',
        backgroundColor: '#000',
    },
    loading: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        color: '#a78bfa',
    },
    spinner: {
        width: '40px',
        height: '40px',
        border: '3px solid #404040',
        borderTop: '3px solid #a78bfa',
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
        marginBottom: '16px',
    },
    subtext: {
        color: '#888',
        fontSize: '14px',
        marginTop: '8px',
    },
    modal: {
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
    },
    modalContent: {
        backgroundColor: '#2d2d2d',
        padding: '24px',
        borderRadius: '12px',
        maxWidth: '400px',
        textAlign: 'center',
    },
    modalTitle: {
        color: '#fff',
        fontSize: '18px',
        marginBottom: '12px',
    },
    modalText: {
        color: '#aaa',
        fontSize: '14px',
        marginBottom: '20px',
        lineHeight: '1.5',
    },
    modalButtons: {
        display: 'flex',
        gap: '12px',
        justifyContent: 'center',
    },
    cancelButton: {
        padding: '10px 20px',
        backgroundColor: '#404040',
        border: 'none',
        borderRadius: '6px',
        color: '#e0e0e0',
        cursor: 'pointer',
        fontSize: '14px',
    },
    confirmButton: {
        padding: '10px 20px',
        backgroundColor: '#dc2626',
        border: 'none',
        borderRadius: '6px',
        color: '#fff',
        cursor: 'pointer',
        fontSize: '14px',
    },
};
