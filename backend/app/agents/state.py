from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import add_messages
from datetime import datetime

class AgentState(TypedDict):
    # Chat History
    messages: List[Any] 
    
    # Project Metadata
    project_id: str
    user_prompt: str
    iteration_count: int
    max_iterations: int
    
    # Artifacts
    blueprint: Dict[str, Any]       # Architect Output
    start_time: str
    
    # Code State
    file_system: Dict[str, str]     # Path -> Content
    
    # Validation States
    security_report: Dict[str, Any] # Sentinel Output
    test_results: Dict[str, Any]    # Oracle Output
    visual_report: Dict[str, Any]   # Watcher Output
    deployment_plan: Dict[str, Any] # Advisor Output
    
    # Loop Control
    current_status: str             # "planning", "coding", "testing", "fixing"
    errors: List[str]               # Accumulated errors to fix
