"""
Planner Agent
Generates explicit multi-step execution plans.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from app.agents.state import ExecutionPlan, PlanStep, StepAction, RiskLevel

logger = logging.getLogger(__name__)


class PlannerAgent:
    """
    Creates structured execution plans from objectives.
    
    Uses Gemini to:
    1. Break down objective into atomic steps
    2. Identify dependencies between steps
    3. Assess risk for each step
    4. Define verification methods
    """
    
    def __init__(self):
        pass
    
    async def create_plan(
        self,
        objective: str,
        context: Dict[str, Any]
    ) -> tuple[ExecutionPlan, Optional[Any]]:

        """
        Generate execution plan for objective.
        
        Args:
            objective: User's high-level goal
            context: Dict with:
                - repo_analysis: From AnalyzerAgent
                - tech_stack: Detected or specified
                - file_system: Current files (if any)
                
        Returns:
            ExecutionPlan with steps
        """
        from app.core.local_model import HybridModelClient
        
        try:
            client = HybridModelClient()
            
            # Build planning prompt
            prompt = self._build_planning_prompt(objective, context)
            
            logger.info(f"Generating plan for: {objective}")
            
            response = await client.generate(prompt, json_mode=True)
            
            # Parse response using safe_parse_json
            from app.core.schema_validator import safe_parse_json, validate_plan
            
            plan_dict, parse_error = safe_parse_json(response)
            if plan_dict is None:
                raise ValueError(f"Failed to parse plan JSON: {parse_error}")
            
            # Validate against plan schema
            plan_dict, warnings = validate_plan(plan_dict)
            if plan_dict is None:
                raise ValueError(f"Plan validation failed: {warnings}")
            if warnings:
                logger.warning(f"Plan validated with {len(warnings)} warnings: {warnings[:3]}")
            
            # Convert to PlanStep objects
            steps = []
            for step in plan_dict.get("steps", []):
                # Handle enum conversion safely
                try:
                    action = StepAction(step["action"])
                except ValueError:
                    action = StepAction.MODIFY # Default
                    
                try:
                    risk = RiskLevel(step["risk_level"])
                except ValueError:
                    risk = RiskLevel.LOW # Default
                
                steps.append(PlanStep(
                    id=step["id"],
                    action=action,
                    intent=step["intent"],
                    target_files=step.get("target_files", []),
                    dependencies=step.get("dependencies", []),
                    risk_level=risk,
                    verification_method=step.get("verification_method", "Manual review"),
                    estimated_tokens=step.get("estimated_tokens", 500),
                    rationale=step.get("rationale", ""),
                    rollback_strategy=step.get("rollback_strategy", "git reset")
                ))
            
            plan = ExecutionPlan(
                objective=objective,
                strategy=plan_dict.get("strategy", "AI Generated Strategy"),
                steps=steps,
                total_estimated_tokens=plan_dict.get("total_estimated_tokens", 0),
                estimated_duration_minutes=plan_dict.get("estimated_duration_minutes", 10),
                risk_assessment=plan_dict.get("risk_assessment", "Low"),
                created_at=datetime.now().isoformat()
            )
            
            # Capture Thought Signature
            from app.core.thought_signature import capture_signature
            signature = await capture_signature(
                agent_name="PLANNER",
                prompt=prompt,
                response=response, # Use full response including signature
                token_usage=len(response) // 4,
                model_used="gemini-2.0-flash-exp"
            )
            
            logger.info(f"Plan created: {len(steps)} steps")
            return plan, signature
            
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            import traceback
            traceback.print_exc()
            # Return fallback simple plan
            return self._create_fallback_plan(objective)
    
    def _build_planning_prompt(self, objective: str, context: Dict) -> str:
        """Build Gemini prompt for planning."""
        
        repo_info = ""
        if context.get("repo_analysis"):
            analysis = context["repo_analysis"]
            tech = analysis.get('tech_stack', {})
            if isinstance(tech, dict):
                tech_str = f"Languages: {tech.get('languages', [])}, Frameworks: {tech.get('frameworks', [])}"
            else:
                tech_str = str(tech)
                
            repo_info = f"""
**Repository Analysis:**
- Tech Stack: {tech_str}
- Key Files: {', '.join(analysis.get('key_files', [])[:10])}
"""
            if 'gemini_analysis' in analysis and isinstance(analysis['gemini_analysis'], dict):
                 repo_info += f"- Relevant Files: {', '.join(analysis['gemini_analysis'].get('relevant_files', []))}\n"
        
        return f"""
You are an expert software architect planning autonomous code changes.

**OBJECTIVE:**
{objective}

{repo_info}

**YOUR TASK:**
Create a detailed, step-by-step execution plan. Each step should be atomic and verifiable.

**RULES:**
1. Keep the plan concise and actionable (prefer 4-6 steps, max 10)
2. Each step must have clear intent
3. Identify dependencies between steps
4. Assess risk for each step
5. Define how to verify success
6. Consider rollback strategies

**OUTPUT FORMAT (JSON):**
{{
  "strategy": "Brief description of overall approach",
  "risk_assessment": "Overall risk level and concerns",
  "total_estimated_tokens": 3000,
  "estimated_duration_minutes": 15,
  "steps": [
    {{
      "id": "s1",
      "action": "create|modify|delete|test|verify|commit",
      "intent": "What this step accomplishes",
      "target_files": ["file1.py", "file2.js"],
      "dependencies": [],
      "risk_level": "low|medium|high|critical",
      "verification_method": "Run pytest|Check output|Manual review",
      "estimated_tokens": 500,
      "rationale": "Why this approach",
      "rollback_strategy": "How to undo if fails"
    }},
    {{
      "id": "s2",
      "action": "test",
      "intent": "Verify changes work",
      "target_files": ["tests/test_new_feature.py"],
      "dependencies": ["s1"],
      "risk_level": "low",
      "verification_method": "All tests pass",
      "estimated_tokens": 200,
      "rationale": "Ensure no regressions",
    }}
  ]
}}

**IMPORTANT**: After your JSON output, include a thought signature:

THOUGHT_SIGNATURE:
{{
  "intent": "Plan execution",
  "rationale": "Why this sequence of steps",
  "confidence": 0.9,
  "alternatives_considered": ["Alternative strategy"],
  "context_used": ["Repo analysis", "Objective"],
  "predicted_outcome": "Successful implementation"
}}

Return ONLY valid JSON followed by the signature.
"""
    
    def _create_fallback_plan(self, objective: str) -> ExecutionPlan:
        """Create simple fallback plan if AI planning fails."""
        return ExecutionPlan(
            objective=objective,
            strategy="Fallback: Simple generation approach",
            steps=[
                PlanStep(
                    id="s1",
                    action=StepAction.CREATE,
                    intent="Generate code based on objective",
                    target_files=["generated_files"],
                    dependencies=[],
                    risk_level=RiskLevel.MEDIUM,
                    verification_method="Manual review",
                    rationale="AI planning unavailable, using fallback"
                ),
                PlanStep(
                    id="s2",
                    action=StepAction.TEST,
                    intent="Run tests if available",
                    target_files=[],
                    dependencies=["s1"],
                    risk_level=RiskLevel.LOW,
                    verification_method="Test suite execution"
                )
            ],
            total_estimated_tokens=1000,
            estimated_duration_minutes=10,
            risk_assessment="MEDIUM - Using fallback plan",
            created_at=datetime.now().isoformat()
        )


# Factory function (replaces singleton for better testability)
def get_planner_agent() -> PlannerAgent:
    """Create a new PlannerAgent instance."""
    return PlannerAgent()
