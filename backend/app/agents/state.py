# app/agents/state.py
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import json

@dataclass
class Issue:
    file: str
    issue: str
    fix: str

class StepAction(str, Enum):
    """Possible step actions."""
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"
    TEST = "test"
    VERIFY = "verify"
    COMMIT = "commit"


class RiskLevel(str, Enum):
    """Risk assessment levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PlanStep:
    """
    Single step in execution plan.
    
    Represents one atomic operation with clear intent.
    """
    id: str                              # Unique step ID (s1, s2, etc.)
    action: StepAction                   # Type of action
    intent: str                          # Why this step exists
    target_files: List[str]              # Files to modify/create
    dependencies: List[str]              # Step IDs that must complete first
    risk_level: RiskLevel                # Risk assessment
    verification_method: str             # How to verify success
    estimated_tokens: int = 0            # Token cost estimate
    rationale: str = ""                  # Technical justification
    rollback_strategy: str = ""          # How to undo if fails
    
    # Execution tracking
    status: str = "pending"              # pending|running|success|failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    commit_sha: Optional[str] = None     # Commit created by this step


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for objective.
    
    Contains ordered steps with dependencies and metadata.
    """
    objective: str                       # User's high-level goal
    strategy: str                        # Overall approach
    steps: List[PlanStep]                # Ordered list of steps
    total_estimated_tokens: int          # Total cost estimate
    estimated_duration_minutes: int      # Time estimate
    risk_assessment: str                 # Overall risk summary
    
    # Metadata
    created_at: str = ""
    created_by: str = "PlannerAgent"
    version: str = "1.0"
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        from dataclasses import asdict
        return asdict(self)
    
    def get_next_step(self) -> Optional[PlanStep]:
        """Get next pending step with satisfied dependencies."""
        completed_ids = {
            step.id for step in self.steps 
            if step.status == "success"
        }
        
        for step in self.steps:
            if step.status != "pending":
                continue
            
            # Check if dependencies satisfied
            deps_satisfied = all(
                dep in completed_ids 
                for dep in step.dependencies
            )
            
            if deps_satisfied:
                return step
        
        return None
    
    def mark_step_complete(self, step_id: str, commit_sha: Optional[str] = None):
        """Mark step as successfully completed."""
        for step in self.steps:
            if step.id == step_id:
                step.status = "success"
                step.completed_at = datetime.now().isoformat()
                step.commit_sha = commit_sha
                break
    
    def mark_step_failed(self, step_id: str, error: str):
        """Mark step as failed."""
        for step in self.steps:
            if step.id == step_id:
                step.status = "failed"
                step.completed_at = datetime.now().isoformat()
                step.error_message = error
                break

@dataclass
class ThoughtSignature:
    """
    Records AI reasoning for decision provenance.
    
    Enables:
    - Understanding why decisions were made
    - Debugging failed reasoning
    - Improving prompts over time
    - Audit compliance
    """
    signature_id: str                    # Unique ID
    agent: str                           # Agent name (Architect, Virtuoso, etc.)
    step_id: Optional[str]               # Associated plan step
    timestamp: str                       # ISO8601 timestamp
    
    # Reasoning
    intent: str                          # What trying to accomplish
    rationale: str                       # Why this approach
    confidence: float                    # 0.0-1.0 certainty
    alternatives_considered: List[str]   # Other approaches rejected
    context_used: List[str]              # Information considered
    predicted_outcome: str               # Expected result
    
    # Metadata
    token_usage: int = 0
    model_used: str = ""
    prompt_hash: Optional[str] = None    # For deduplication
    
    # Actual outcome (filled after execution)
    actual_outcome: Optional[str] = None
    success: Optional[bool] = None
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        from dataclasses import asdict
        return asdict(self)


@dataclass
class AgentState:
    agent_id: str = ""
    messages: List[str] = field(default_factory=list)
    blueprint: str = ""
    
    # Existing fields migrated from TypedDict if needed, or just what user asked
    # User asked for: thought_signature, screenshot_paths, issues
    # And "Add other fields as needed, e.g. 'summary': Optional[str] = None"
    # To maintain compatibility with existing orchestrator, I should add fields used there:
    # project_id, content, tech_stack, file_system, current_status, errors, iteration_count
    # user_prompt etc.
    # But user spec only showed a few fields.
    # However, replacing the *entire* file with just the user's snippet will BREAK the orchestrator 
    # which relies on `file_system`, `project_id`.
    # I MUST include the existing fields in the new dataclass.
    
    # Original fields from previous state.py (inferred from view_file):
    project_id: str = ""
    run_id: str = ""
    user_prompt: str = ""
    iteration_count: int = 0
    max_iterations: int = 3
    tech_stack: Optional[str] = None
    
    # Artifacts
    start_time: str = ""
    
    # Code State
    file_system: Dict[str, str] = field(default_factory=dict)
    
    # Validation States
    security_report: Dict[str, Any] = field(default_factory=dict)
    test_results: Dict[str, Any] = field(default_factory=dict)
    visual_report: Dict[str, Any] = field(default_factory=dict)
    deployment_plan: Dict[str, Any] = field(default_factory=dict)
    
    # Loop Control
    current_status: str = "planning"
    errors: List[str] = field(default_factory=list)
    retry_count: int = 0
    
    # Strategy Engine (Phase 1)
    strategy_history: List[Dict[str, Any]] = field(default_factory=list)
    current_repair_strategy: Optional[str] = None
    total_retries_used: int = 0
    max_total_retries: int = 5
    strategy_engine_state: Optional[Dict[str, Any]] = None  # Serialized StrategyEngine
    
    # Reasoning
    reasoning_history: Optional[List[Dict[str, str]]] = None
    prior_context: Optional[str] = None

    # Added fields per User Request:
    thought_signature: Optional[str] = None # Gemini signature for context continuity
    screenshot_paths: Dict[int, str] = field(default_factory=dict) # step->image path
    issues: List[Issue] = field(default_factory=list) # QA/security issues
    
    # Decision Provenance
    thought_signatures: List[ThoughtSignature] = field(default_factory=list)
    
    # Git Integration
    repo_path: Optional[str] = None  # Path to cloned repository
    repo_url: Optional[str] = None   # Original repository URL
    current_branch: Optional[str] = None  # Branch created for work
    feature_branch: Optional[str] = None  # Feature branch name for autonomous execution
    commit_history: List[str] = field(default_factory=list)  # List of commit SHAs
    initial_commit: Optional[str] = None  # Starting commit for rollback
    
    # Planning
    execution_plan: Optional[ExecutionPlan] = None
    current_step_id: Optional[str] = None
    
    # Metrics (Phase 6)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Release & Preview
    release_report: Optional[Dict[str, Any]] = None
    preview_port: Optional[int] = None
    deployment_report: Optional[Dict[str, Any]] = None
    
    # Incremental tracking
    changed_files: List[str] = field(default_factory=list)  # Files modified in last Virtuoso pass
    
    # Metadata from CheckpointManager
    _checkpoint_meta: Optional[Dict[str, Any]] = None
    
    def json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))
    
    @classmethod
    def parse_raw(cls, json_str: str) -> 'AgentState':
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        # Handle nested dataclasses manually if needed, or let constructor handle dicts if simple
        # Issue is a dataclass, so we need to convert list of dicts to list of Issues
        if 'issues' in data and data['issues']:
            issues_data = data['issues']
            data['issues'] = [Issue(**i) if isinstance(i, dict) else i for i in issues_data]
            
        if 'execution_plan' in data and data['execution_plan']:
            plan_data = data['execution_plan']
            if isinstance(plan_data, dict):
                # Handle nested steps list
                if 'steps' in plan_data:
                    steps_data = plan_data['steps']
                    plan_data['steps'] = [PlanStep(**s) if isinstance(s, dict) else s for s in steps_data]
                data['execution_plan'] = ExecutionPlan(**plan_data)
        
        if 'thought_signatures' in data and data['thought_signatures']:
            sigs_data = data['thought_signatures']
            data['thought_signatures'] = [ThoughtSignature(**s) if isinstance(s, dict) else s for s in sigs_data]
            
        return cls(**data)

    # Dictionary access compatibility for LangGraph 
    # LangGraph often treats state as dict. 
    # If we use dataclass, we might need to implement __getitem__ etc if the graph expects it.
    # But usually LangGraph supports Pydantic models or TypedDict. Dataclasses ok?
    # User requested Dataclass.
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)
