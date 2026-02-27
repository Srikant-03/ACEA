export interface Issue {
    file: string;
    issue: string;
    fix: string;
}

export interface AgentState {
    // Core identification
    project_id: string;
    agent_id?: string;
    run_id?: string;
    user_prompt: string;
    tech_stack?: string;
    start_time?: string;

    // Status & loop control
    current_status: string;
    messages: string[];
    iteration_count: number;
    max_iterations: number;
    errors: string[];
    retry_count: number;

    // Artifacts
    blueprint?: any;
    file_system: Record<string, string>;

    // Validation states
    security_report?: any;
    visual_report?: any;
    test_results?: any;
    deployment_plan?: any;
    screenshot_paths?: Record<number, string>;

    // Reasoning & provenance
    thought_signature?: string;
    thought_signatures?: any[];
    reasoning_history?: Array<Record<string, string>>;
    prior_context?: string;

    // Planning
    execution_plan?: any[];
    current_step_id?: string;

    // Git integration
    repo_url?: string;
    repo_path?: string;
    feature_branch?: string;
    current_branch?: string;
    commit_history?: any[];
    initial_commit?: string;

    // QA
    issues?: any[];
    analysis?: any;
}

export type Event =
    | { type: "log"; text: string; agent?: string; timestamp?: string }
    | { type: "status"; agent: string; status: "idle" | "running" | "success" | "error" }
    | { type: "state_update"; state: AgentState }
    | { type: "agent_log"; agent_name: string; message: string; metadata?: any }
    | { type: "metrics"; data: any };
