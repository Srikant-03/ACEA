from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import add_messages
from datetime import datetime
import json
import re

class AgentState(TypedDict):
    # Chat History
    messages: List[Any] 
    
    # Project Metadata
    project_id: str
    user_prompt: str
    iteration_count: int
    max_iterations: int
    tech_stack: Optional[str]
    
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
    
    # ===== REASONING MEMORY (Optional) =====
    reasoning_history: Optional[List[Dict[str, str]]]  # Chronicle of agent thoughts
    prior_context: Optional[str]                       # Last agent's reasoning for immediate reuse


# ===== STATE MEMORY HELPERS =====
# These methods operate on state dictionaries to enable reasoning continuity
# They are additive and do not affect existing state serialization

def record_thought(state: AgentState, agent_name: str, llm_output: str) -> None:
    """
    Extract and store lightweight reasoning from an LLM response.
    
    This function:
    - Extracts a reasoning snippet from the LLM output
    - Adds it to reasoning_history
    - Updates prior_context for immediate reuse
    - Does nothing if extraction fails (safe fallback)
    
    Args:
        state: The current agent state
        agent_name: Name of the agent (e.g., "architect", "virtuoso")
        llm_output: The raw LLM response text
    
    Side Effects:
        Mutates state['reasoning_history'] and state['prior_context'] in place
    """
    # Initialize history if not present
    if state.get('reasoning_history') is None:
        state['reasoning_history'] = []
    
    # Extract reasoning (first 200 chars as lightweight snapshot)
    thought_snippet = _extract_reasoning(llm_output)
    
    if not thought_snippet:
        return  # Safe no-op if extraction fails
    
    # Record in history
    state['reasoning_history'].append({
        "agent": agent_name,
        "thought": thought_snippet,
        "timestamp": datetime.now().isoformat()
    })
    
    # Update prior context for immediate reuse
    state['prior_context'] = f"[{agent_name}]: {thought_snippet}"


def inject_memory(state: AgentState, prompt: str) -> str:
    """
    Prepend prior reasoning context to a prompt if it exists.
    
    This function:
    - Checks if prior_context exists in state
    - If yes, prepends it to the prompt
    - If no, returns the prompt unchanged
    - Never modifies the original prompt structure
    
    Args:
        state: The current agent state
        prompt: The original prompt to be sent to the LLM
    
    Returns:
        Augmented prompt with memory context, or original prompt if no memory exists
    """
    prior = state.get('prior_context')
    
    if not prior:
        return prompt  # No memory, return unchanged
    
    # Prepend memory context
    memory_context = f"## Previous Agent Reasoning:\n{prior}\n\n## Current Task:\n"
    return memory_context + prompt


def _extract_reasoning(llm_output: str) -> str:
    """
    Internal helper to extract a lightweight reasoning snippet from LLM output.
    
    Strategy:
    - Take the first 200 characters of the response
    - Strip markdown formatting
    - Remove excessive whitespace
    
    This is intentionally simple to avoid parsing errors.
    
    Args:
        llm_output: Raw LLM response text
    
    Returns:
        Cleaned reasoning snippet, or empty string if extraction fails
    """
    if not llm_output or not isinstance(llm_output, str):
        return ""
    
    # Remove markdown code blocks
    cleaned = re.sub(r'```[\s\S]*?```', '', llm_output)
    
    # Remove markdown headers
    cleaned = re.sub(r'#+\s*', '', cleaned)
    
    # Take first 200 chars
    snippet = cleaned[:200].strip()
    
    # Remove excessive whitespace
    snippet = ' '.join(snippet.split())
    
    return snippet