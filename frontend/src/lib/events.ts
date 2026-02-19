export interface Issue {
    file: string;
    issue: string;
    fix: string;
}

export interface AgentState {
    project_id: string;
    run_id?: string;
    current_status: string;
    messages: string[];
    blueprint?: any;
    user_prompt: string;
    file_system: Record<string, string>;
    iteration_count: number;
    max_iterations: number;
    errors: string[];
    security_report?: any;
    visual_report?: any;
    screenshot_paths?: Record<number, string>; // Optional for later

    // New metrics
    retry_count: number;
}

export type Event =
    | { type: "log"; text: string; agent?: string; timestamp?: string }
    | { type: "status"; agent: string; status: "idle" | "running" | "success" | "error" }
    | { type: "state_update"; state: AgentState }
    | { type: "agent_log"; agent_name: string; message: string; metadata?: any }
    | { type: "metrics"; data: any };
