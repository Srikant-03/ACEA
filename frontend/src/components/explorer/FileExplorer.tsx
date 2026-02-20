'use client';

import React, { useState, useCallback } from 'react';

export interface FileNode {
    name: string;
    path: string;
    type: 'file' | 'directory';
    children?: FileNode[];
    size?: number;
    modified?: string;
}

interface FileExplorerProps {
    projectId: string;
    files: FileNode;
    onFileSelect?: (path: string) => void;
    onFileCreate?: (path: string, type: 'file' | 'directory') => void;
    onFileDelete?: (path: string) => void;
    onFileRename?: (oldPath: string, newPath: string) => void;
    onRefresh?: () => void;
    readOnly?: boolean;
}

interface FileContextMenu {
    x: number;
    y: number;
    node: FileNode;
}

export default function FileExplorer({
    projectId,
    files,
    onFileSelect,
    onFileCreate,
    onFileDelete,
    onFileRename,
    onRefresh,
    readOnly = false
}: FileExplorerProps) {
    const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['project']));
    const [selectedPath, setSelectedPath] = useState<string | null>(null);
    const [contextMenu, setContextMenu] = useState<FileContextMenu | null>(null);
    const [renamingPath, setRenamingPath] = useState<string | null>(null);
    const [newName, setNewName] = useState('');
    const [isCreating, setIsCreating] = useState<'file' | 'directory' | null>(null);
    const [createPath, setCreatePath] = useState<string>('');

    // Toggle directory expansion
    const toggleExpand = (path: string) => {
        setExpandedPaths(prev => {
            const next = new Set(prev);
            if (next.has(path)) {
                next.delete(path);
            } else {
                next.add(path);
            }
            return next;
        });
    };

    // Handle file/folder click
    const handleClick = (node: FileNode) => {
        if (node.type === 'directory') {
            toggleExpand(node.path);
        } else {
            setSelectedPath(node.path);
            onFileSelect?.(node.path);
        }
    };

    // Handle right-click context menu
    const handleContextMenu = (e: React.MouseEvent, node: FileNode) => {
        e.preventDefault();
        if (readOnly) return;
        setContextMenu({ x: e.clientX, y: e.clientY, node });
    };

    // Close context menu
    const closeContextMenu = useCallback(() => {
        setContextMenu(null);
    }, []);

    // Handle rename
    const handleRename = () => {
        if (!contextMenu) return;
        setRenamingPath(contextMenu.node.path);
        setNewName(contextMenu.node.name);
        closeContextMenu();
    };

    // Submit rename
    const submitRename = (e: React.FormEvent) => {
        e.preventDefault();
        if (renamingPath && newName && newName !== renamingPath.split('/').pop()) {
            const parentPath = renamingPath.split('/').slice(0, -1).join('/');
            const newPath = parentPath ? `${parentPath}/${newName}` : newName;
            onFileRename?.(renamingPath, newPath);
        }
        setRenamingPath(null);
        setNewName('');
    };

    // Handle delete
    const handleDelete = () => {
        if (!contextMenu) return;
        if (confirm(`Delete ${contextMenu.node.name}?`)) {
            onFileDelete?.(contextMenu.node.path);
        }
        closeContextMenu();
    };

    // Handle create new file/folder
    const handleCreate = (type: 'file' | 'directory') => {
        const basePath = contextMenu?.node.type === 'directory'
            ? contextMenu.node.path
            : contextMenu?.node.path.split('/').slice(0, -1).join('/') || '';

        setCreatePath(basePath);
        setIsCreating(type);
        closeContextMenu();
    };

    // Submit create
    const submitCreate = (e: React.FormEvent) => {
        e.preventDefault();
        if (newName && isCreating) {
            const fullPath = createPath ? `${createPath}/${newName}` : newName;
            onFileCreate?.(fullPath, isCreating);
        }
        setIsCreating(null);
        setNewName('');
    };

    // Get file icon based on extension
    const getFileIcon = (name: string, isDirectory: boolean): string => {
        if (isDirectory) return '📁';

        const ext = name.split('.').pop()?.toLowerCase();
        const icons: Record<string, string> = {
            'js': '🟨',
            'jsx': '⚛️',
            'ts': '🔷',
            'tsx': '⚛️',
            'py': '🐍',
            'json': '📋',
            'html': '🌐',
            'css': '🎨',
            'scss': '🎨',
            'md': '📝',
            'yml': '⚙️',
            'yaml': '⚙️',
            'env': '🔐',
            'png': '🖼️',
            'jpg': '🖼️',
            'svg': '🎯',
            'gif': '🖼️',
            'lock': '🔒',
        };

        return icons[ext || ''] || '📄';
    };

    // Render file tree node
    const renderNode = (node: FileNode, depth: number = 0): React.ReactNode => {
        const isExpanded = expandedPaths.has(node.path);
        const isSelected = selectedPath === node.path;
        const isRenaming = renamingPath === node.path;

        return (
            <div key={node.path}>
                <div
                    style={{
                        ...styles.node,
                        paddingLeft: `${depth * 16 + 8}px`,
                        backgroundColor: isSelected ? '#37373d' : 'transparent',
                    }}
                    onClick={() => handleClick(node)}
                    onContextMenu={(e) => handleContextMenu(e, node)}
                    className="file-node"
                >
                    {/* Expand/collapse arrow for directories */}
                    {node.type === 'directory' ? (
                        <span style={styles.arrow}>
                            {isExpanded ? '▼' : '▶'}
                        </span>
                    ) : (
                        <span style={styles.arrow} />
                    )}

                    {/* Icon */}
                    <span style={styles.icon}>
                        {node.type === 'directory' && isExpanded ? '📂' : getFileIcon(node.name, node.type === 'directory')}
                    </span>

                    {/* Name (editable if renaming) */}
                    {isRenaming ? (
                        <form onSubmit={submitRename} style={{ flex: 1 }}>
                            <input
                                type="text"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                                onBlur={() => setRenamingPath(null)}
                                autoFocus
                                style={styles.renameInput}
                            />
                        </form>
                    ) : (
                        <span style={styles.name}>{node.name}</span>
                    )}

                    {/* Action icons on hover */}
                    {!readOnly && (
                        <div style={styles.actions} className="file-actions">
                            {node.type === 'directory' && (
                                <>
                                    <button
                                        style={styles.actionButton}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setExpandedPaths(prev => new Set([...prev, node.path]));
                                            setCreatePath(node.path);
                                            setIsCreating('file');
                                        }}
                                        title="New File"
                                    >
                                        📝
                                    </button>
                                    <button
                                        style={styles.actionButton}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setExpandedPaths(prev => new Set([...prev, node.path]));
                                            setCreatePath(node.path);
                                            setIsCreating('directory');
                                        }}
                                        title="New Folder"
                                    >
                                        📁
                                    </button>
                                </>
                            )}
                        </div>
                    )}
                </div>

                {/* Children */}
                {node.type === 'directory' && isExpanded && node.children && (
                    <div>
                        {node.children
                            .sort((a, b) => {
                                // Directories first, then alphabetically
                                if (a.type !== b.type) {
                                    return a.type === 'directory' ? -1 : 1;
                                }
                                return a.name.localeCompare(b.name);
                            })
                            .map(child => renderNode(child, depth + 1))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div style={styles.container} onClick={closeContextMenu}>
            {/* Header */}
            <div style={styles.header}>
                <span style={styles.title}>Explorer</span>
                <div style={styles.headerActions}>
                    {!readOnly && (
                        <>
                            <button
                                style={styles.headerButton}
                                onClick={() => {
                                    setCreatePath('project');
                                    setIsCreating('file');
                                }}
                                title="New File"
                            >
                                📝
                            </button>
                            <button
                                style={styles.headerButton}
                                onClick={() => {
                                    setCreatePath('project');
                                    setIsCreating('directory');
                                }}
                                title="New Folder"
                            >
                                📁
                            </button>
                        </>
                    )}
                    <button
                        style={styles.headerButton}
                        onClick={onRefresh}
                        title="Refresh"
                    >
                        🔄
                    </button>
                </div>
            </div>

            {/* File Tree */}
            <div style={styles.tree}>
                {renderNode(files)}
            </div>

            {/* Create input */}
            {isCreating && (
                <div style={styles.createOverlay}>
                    <form onSubmit={submitCreate} style={styles.createForm}>
                        <span>{isCreating === 'file' ? '📄' : '📁'}</span>
                        <input
                            type="text"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            placeholder={`New ${isCreating}...`}
                            autoFocus
                            style={styles.createInput}
                        />
                        <button type="submit" style={styles.createButton}>✓</button>
                        <button
                            type="button"
                            onClick={() => setIsCreating(null)}
                            style={styles.createButton}
                        >
                            ✕
                        </button>
                    </form>
                </div>
            )}

            {/* Context Menu */}
            {contextMenu && (
                <div
                    style={{
                        ...styles.contextMenu,
                        left: contextMenu.x,
                        top: contextMenu.y,
                    }}
                    onClick={(e) => e.stopPropagation()}
                >
                    {contextMenu.node.type === 'directory' && (
                        <>
                            <button style={styles.menuItem} onClick={() => handleCreate('file')}>
                                📝 New File
                            </button>
                            <button style={styles.menuItem} onClick={() => handleCreate('directory')}>
                                📁 New Folder
                            </button>
                            <div style={styles.menuDivider} />
                        </>
                    )}
                    <button style={styles.menuItem} onClick={handleRename}>
                        ✏️ Rename
                    </button>
                    <button style={{ ...styles.menuItem, color: '#f14c4c' }} onClick={handleDelete}>
                        🗑️ Delete
                    </button>
                </div>
            )}

            <style>{`
        .file-node:hover {
          background-color: #2a2a2a !important;
        }
        .file-node:hover .file-actions {
          opacity: 1;
        }
        .file-actions {
          opacity: 0;
          transition: opacity 0.15s;
        }
      `}</style>
        </div>
    );
}

const styles: { [key: string]: React.CSSProperties } = {
    container: {
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        backgroundColor: '#1e1e1e',
        color: '#cccccc',
        fontSize: '13px',
        fontFamily: '-apple-system, BlinkMacSystemFont, Inter, sans-serif',
    },
    header: {
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 12px',
        borderBottom: '1px solid #3c3c3c',
        backgroundColor: '#252526',
    },
    title: {
        fontWeight: 600,
        textTransform: 'uppercase',
        fontSize: '11px',
        letterSpacing: '0.5px',
        color: '#888',
    },
    headerActions: {
        display: 'flex',
        gap: '4px',
    },
    headerButton: {
        background: 'none',
        border: 'none',
        padding: '4px',
        cursor: 'pointer',
        fontSize: '14px',
        borderRadius: '4px',
    },
    tree: {
        flex: 1,
        overflow: 'auto',
        paddingTop: '4px',
    },
    node: {
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        padding: '4px 8px',
        cursor: 'pointer',
        userSelect: 'none',
    },
    arrow: {
        width: '14px',
        fontSize: '8px',
        color: '#888',
        textAlign: 'center',
    },
    icon: {
        fontSize: '14px',
        width: '20px',
        textAlign: 'center',
    },
    name: {
        flex: 1,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
    },
    actions: {
        display: 'flex',
        gap: '2px',
    },
    actionButton: {
        background: 'none',
        border: 'none',
        padding: '2px 4px',
        cursor: 'pointer',
        fontSize: '12px',
        borderRadius: '2px',
    },
    renameInput: {
        background: '#3c3c3c',
        border: '1px solid #007acc',
        color: '#fff',
        padding: '2px 4px',
        fontSize: '13px',
        borderRadius: '2px',
        outline: 'none',
        width: '100%',
    },
    createOverlay: {
        position: 'absolute',
        bottom: '0',
        left: '0',
        right: '0',
        backgroundColor: '#252526',
        borderTop: '1px solid #3c3c3c',
        padding: '8px',
    },
    createForm: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
    },
    createInput: {
        flex: 1,
        background: '#3c3c3c',
        border: '1px solid #007acc',
        color: '#fff',
        padding: '6px 8px',
        fontSize: '13px',
        borderRadius: '4px',
        outline: 'none',
    },
    createButton: {
        background: 'none',
        border: 'none',
        color: '#888',
        cursor: 'pointer',
        padding: '4px 8px',
        fontSize: '14px',
    },
    contextMenu: {
        position: 'fixed',
        backgroundColor: '#252526',
        border: '1px solid #3c3c3c',
        borderRadius: '6px',
        padding: '4px',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
        zIndex: 1000,
        minWidth: '140px',
    },
    menuItem: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        width: '100%',
        padding: '8px 12px',
        background: 'none',
        border: 'none',
        color: '#cccccc',
        cursor: 'pointer',
        fontSize: '13px',
        textAlign: 'left',
        borderRadius: '4px',
    },
    menuDivider: {
        height: '1px',
        backgroundColor: '#3c3c3c',
        margin: '4px 0',
    },
};
