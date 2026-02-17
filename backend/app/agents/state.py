# app/agents/state.py
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict
import json

@dataclass
class Issue:
    file: str
    issue: str
    fix: str

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
    
    # Reasoning
    reasoning_history: Optional[List[Dict[str, str]]] = None
    prior_context: Optional[str] = None

    # Added fields per User Request:
    thought_signature: Optional[str] = None # Gemini signature for context continuity
    screenshot_paths: Dict[int, str] = field(default_factory=dict) # step->image path
    issues: List[Issue] = field(default_factory=list) # QA/security issues
    
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
