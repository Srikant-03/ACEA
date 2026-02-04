export type AgentName = 'ARCHITECT' | 'VIRTUOSO' | 'SENTINEL' | 'ORACLE' | 'WATCHER' | 'ADVISOR' | 'SYSTEM';
export type AgentStatus = 'idle' | 'working' | 'success' | 'error';
export type LogLevel = 'success' | 'info' | 'warning' | 'error';

export interface AgentLog {
    agent_name: string;
    message: string;
    timestamp?: string;
}

export interface AgentStatusUpdate {
    agent_name: AgentName;
    status: AgentStatus;
}

export interface MissionAccepted {
    project_id: string;
}

export interface MissionComplete {
    project_id: string;
    files?: Record<string, string>;
}

export interface MissionError {
    detail: string;
    error_code?: string;
}

export interface GenerationStarted {
    total_files: number;
    file_list: string[];
}

export interface FileGenerated {
    file_path: string;
    content: string;
    index: number;
    total: number;
}

export type AgentsState = Record<AgentName, AgentStatus>;

export interface LogEntry {
    id: string;
    agent: string;
    message: string;
    type: LogLevel;
    timestamp: Date;
}
