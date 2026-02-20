'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import '@xterm/xterm/css/xterm.css';

interface TerminalTab {
    id: string;
    name: string;
    terminal: XTerm;
    fitAddon: FitAddon;
    history: string[];
}

interface MultiTabTerminalProps {
    projectId: string;
    websocketUrl?: string;
    onCommand?: (command: string) => void;
    readOnly?: boolean;
}

export default function MultiTabTerminal({
    projectId,
    websocketUrl,
    onCommand,
    readOnly = false
}: MultiTabTerminalProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [tabs, setTabs] = useState<TerminalTab[]>([]);
    const [activeTabId, setActiveTabId] = useState<string | null>(null);
    const [isConnected, setIsConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectCountRef = useRef(0);

    // Create a new terminal tab
    const createTerminalTab = useCallback((name?: string) => {
        const id = `term_${Date.now()}`;
        const terminal = new XTerm({
            theme: {
                background: '#1e1e1e',
                foreground: '#d4d4d4',
                cursor: '#d4d4d4',
                cursorAccent: '#1e1e1e',
                selectionBackground: '#264f78',
                black: '#000000',
                red: '#cd3131',
                green: '#0dbc79',
                yellow: '#e5e510',
                blue: '#2472c8',
                magenta: '#bc3fbc',
                cyan: '#11a8cd',
                white: '#e5e5e5',
                brightBlack: '#666666',
                brightRed: '#f14c4c',
                brightGreen: '#23d18b',
                brightYellow: '#f5f543',
                brightBlue: '#3b8eea',
                brightMagenta: '#d670d6',
                brightCyan: '#29b8db',
                brightWhite: '#ffffff',
            },
            fontFamily: 'JetBrains Mono, Menlo, Monaco, Consolas, monospace',
            fontSize: 13,
            lineHeight: 1.3,
            cursorBlink: true,
            cursorStyle: 'bar',
            scrollback: 10000,
        });

        const fitAddon = new FitAddon();
        terminal.loadAddon(fitAddon);
        terminal.loadAddon(new WebLinksAddon());

        const newTab: TerminalTab = {
            id,
            name: name || `Terminal ${tabs.length + 1}`,
            terminal,
            fitAddon,
            history: [],
        };

        setTabs(prev => [...prev, newTab]);
        setActiveTabId(id);

        return newTab;
    }, [tabs.length]);

    // Initialize first terminal
    useEffect(() => {
        if (tabs.length === 0) {
            createTerminalTab('Main');
        }
    }, [tabs.length, createTerminalTab]);

    // Mount active terminal to container
    useEffect(() => {
        if (!containerRef.current || !activeTabId) return;

        const activeTab = tabs.find(t => t.id === activeTabId);
        if (!activeTab) return;

        // Clear container
        containerRef.current.innerHTML = '';

        // Mount terminal
        activeTab.terminal.open(containerRef.current);
        activeTab.fitAddon.fit();

        // Welcome message
        if (activeTab.history.length === 0) {
            activeTab.terminal.writeln('\x1b[1;36m╔════════════════════════════════════════╗\x1b[0m');
            activeTab.terminal.writeln('\x1b[1;36m║\x1b[1;35m    ACEA Sentinel Terminal             \x1b[1;36m║\x1b[0m');
            activeTab.terminal.writeln('\x1b[1;36m╚════════════════════════════════════════╝\x1b[0m');
            activeTab.terminal.writeln('');
            activeTab.terminal.write('\x1b[1;32m$ \x1b[0m');
        }

        // Handle resize
        const handleResize = () => activeTab.fitAddon.fit();
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
        };
    }, [activeTabId, tabs]);

    // WebSocket connection for PTY streaming
    useEffect(() => {
        if (!websocketUrl) return;

        const connect = () => {
            const ws = new WebSocket(websocketUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                setIsConnected(true);
                reconnectCountRef.current = 0;
                console.log('Terminal WebSocket connected');
            };

            ws.onmessage = (event) => {
                const activeTab = tabs.find(t => t.id === activeTabId);
                if (activeTab) {
                    activeTab.terminal.write(event.data);
                }
            };

            ws.onclose = () => {
                setIsConnected(false);
                // Attempt reconnect with exponential backoff
                const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 30000);
                reconnectCountRef.current++;
                setTimeout(connect, delay);
            };

            ws.onerror = (error) => {
                console.error('Terminal WebSocket error:', error);
            };
        };

        connect();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [websocketUrl, activeTabId, tabs]);

    // Cleanup tabs when switching to Read-Only (Preview Mode)
    useEffect(() => {
        if (readOnly) {
            // Dispose all tabs except Main
            const mainTab = tabs.find(t => t.name === 'Main');
            const otherTabs = tabs.filter(t => t.name !== 'Main');

            otherTabs.forEach(t => {
                t.terminal.dispose();
            });

            if (mainTab) {
                setTabs([mainTab]);
                setActiveTabId(mainTab.id);
            } else if (tabs.length > 0) {
                setTabs([]);
                setActiveTabId(null);
            }
        }
    }, [readOnly]);

    // Handle keyboard input
    useEffect(() => {
        const activeTab = tabs.find(t => t.id === activeTabId);
        if (!activeTab) return;

        let currentLine = '';

        const disposable = activeTab.terminal.onData((data) => {
            if (readOnly) return;

            // Handle Enter key
            if (data === '\r') {
                activeTab.terminal.writeln('');
                if (currentLine.trim()) {
                    activeTab.history.push(currentLine);

                    // Send via WebSocket or callback
                    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                        wsRef.current.send(currentLine + '\n');
                    } else if (onCommand) {
                        onCommand(currentLine);
                    }
                }
                currentLine = '';
                activeTab.terminal.write('\x1b[1;32m$ \x1b[0m');
            }
            // Handle Backspace
            else if (data === '\x7f') {
                if (currentLine.length > 0) {
                    currentLine = currentLine.slice(0, -1);
                    activeTab.terminal.write('\b \b');
                }
            }
            // Handle Ctrl+C
            else if (data === '\x03') {
                activeTab.terminal.writeln('^C');
                currentLine = '';
                activeTab.terminal.write('\x1b[1;32m$ \x1b[0m');
            }
            // Handle Ctrl+L (clear)
            else if (data === '\x0c') {
                activeTab.terminal.clear();
                activeTab.terminal.write('\x1b[1;32m$ \x1b[0m');
            }
            // Regular characters
            else if (data >= ' ') {
                currentLine += data;
                activeTab.terminal.write(data);
            }
        });

        return () => disposable.dispose();
    }, [activeTabId, tabs, onCommand, readOnly]);

    // Close a tab
    const closeTab = (tabId: string, e: React.MouseEvent) => {
        e.stopPropagation();

        const tabIndex = tabs.findIndex(t => t.id === tabId);
        if (tabIndex === -1) return;

        const tab = tabs[tabIndex];
        tab.terminal.dispose();

        const newTabs = tabs.filter(t => t.id !== tabId);
        setTabs(newTabs);

        // If closing active tab, switch to another
        if (activeTabId === tabId && newTabs.length > 0) {
            const newActiveIndex = Math.min(tabIndex, newTabs.length - 1);
            setActiveTabId(newTabs[newActiveIndex].id);
        } else if (newTabs.length === 0) {
            // Create a new tab if all closed
            createTerminalTab('Main');
        }
    };

    // Rename a tab
    const renameTab = (tabId: string, newName: string) => {
        setTabs(prev => prev.map(t =>
            t.id === tabId ? { ...t, name: newName } : t
        ));
    };

    return (
        <div style={styles.container}>
            {/* Tab Bar */}
            <div style={styles.tabBar}>
                <div style={styles.tabs}>
                    {tabs.map((tab) => (
                        <div
                            key={tab.id}
                            style={{
                                ...styles.tab,
                                ...(tab.id === activeTabId ? styles.activeTab : {}),
                            }}
                            onClick={() => setActiveTabId(tab.id)}
                        >
                            <span style={styles.tabIcon}>⬛</span>
                            <span style={styles.tabName}>{tab.name}</span>
                            {!readOnly && tabs.length > 1 && (
                                <button
                                    style={styles.closeButton}
                                    onClick={(e) => closeTab(tab.id, e)}
                                    title="Close tab"
                                >
                                    ×
                                </button>
                            )}
                        </div>
                    ))}
                    {!readOnly && (
                        <button
                            style={styles.newTabButton}
                            onClick={() => createTerminalTab()}
                            title="New terminal"
                        >
                            +
                        </button>
                    )}
                </div>

                <div style={styles.statusBar}>
                    <span style={{
                        ...styles.statusIndicator,
                        backgroundColor: isConnected ? '#0dbc79' : '#666',
                    }} />
                    <span style={styles.statusText}>
                        {isConnected ? 'Connected' : 'Local'}
                    </span>
                </div>
            </div>

            {/* Terminal Container */}
            <div ref={containerRef} style={styles.terminalContainer} />
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
    tabBar: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: '#252526',
        borderBottom: '1px solid #3c3c3c',
        minHeight: '36px',
    },
    tabs: {
        display: 'flex',
        alignItems: 'center',
        gap: '2px',
        padding: '4px',
        overflowX: 'auto',
        flex: 1,
    },
    tab: {
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '6px 12px',
        backgroundColor: '#2d2d2d',
        borderRadius: '4px 4px 0 0',
        cursor: 'pointer',
        transition: 'background-color 0.15s',
        whiteSpace: 'nowrap',
        fontSize: '12px',
        color: '#888',
    },
    activeTab: {
        backgroundColor: '#1e1e1e',
        color: '#fff',
    },
    tabIcon: {
        fontSize: '10px',
        opacity: 0.6,
    },
    tabName: {
        maxWidth: '120px',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
    },
    closeButton: {
        background: 'none',
        border: 'none',
        color: '#888',
        cursor: 'pointer',
        padding: '0 2px',
        fontSize: '16px',
        lineHeight: 1,
        borderRadius: '2px',
    },
    newTabButton: {
        background: 'none',
        border: 'none',
        color: '#888',
        cursor: 'pointer',
        padding: '4px 10px',
        fontSize: '18px',
        borderRadius: '4px',
    },
    statusBar: {
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        padding: '0 12px',
    },
    statusIndicator: {
        width: '8px',
        height: '8px',
        borderRadius: '50%',
    },
    statusText: {
        fontSize: '11px',
        color: '#888',
    },
    terminalContainer: {
        flex: 1,
        padding: '8px',
        minHeight: 0,
    },
};
