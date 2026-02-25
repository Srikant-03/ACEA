"""
Resume Engine — Robust Checkpoint Resume with Validation & Mid-Plan Re-Entry

Handles the complex process of resuming an interrupted autonomous pipeline:
1. Loads and validates checkpoint state
2. Reconnects to Git repository (verifies branch and HEAD)
3. Identifies the last completed step and determines the correct graph entry node
4. Rebuilds StrategyEngine from serialized state
5. Verifies filesystem matches checkpoint expectations
6. Returns a validated state ready for graph re-entry

This replaces the naive load-and-restart approach with intelligent partial recovery.
"""

import logging
import os
from typing import Tuple, Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from app.core.sandbox_guard import SandboxGuard

logger = logging.getLogger(__name__)

# Node mapping: execution_plan step types → graph node names
STEP_TO_NODE = {
    "architect": "architect",
    "planning": "planner",
    "plan": "planner",
    "generate": "virtuoso",
    "code_generation": "virtuoso",
    "implementation": "virtuoso",
    "validation": "sentinel",
    "audit": "sentinel",
    "security": "sentinel",
    "testing": "testing",
    "test": "testing",
    "review": "advisor",
    "advisory": "advisor",
    "visual": "watcher",
    "watch": "watcher",
    "deploy": "release",
    "release": "release",
}


class ResumeValidationError(Exception):
    """Raised when checkpoint state is invalid for resuming."""
    pass


class ResumeEngine:
    """
    Robust checkpoint-resume with validation and partial recovery.
    
    Usage:
        engine = ResumeEngine()
        state, entry_node = await engine.resume(job_id)
        # Feed state into graph.astream(state, config) starting at entry_node
    """
    
    REQUIRED_FIELDS = [
        "project_id", "user_prompt", "iteration_count", 
        "max_iterations", "file_system", "errors"
    ]
    
    def __init__(self):
        from app.core.persistence import get_checkpoint_manager
        self.checkpoint_mgr = get_checkpoint_manager()
    
    async def resume(self, job_id: str) -> Tuple[Any, str]:
        """
        Full resume flow — returns (validated_state, entry_node_name).
        
        Args:
            job_id: The checkpoint/job identifier
            
        Returns:
            Tuple of (AgentState, node_name) ready for graph re-entry
            
        Raises:
            ResumeValidationError: If checkpoint is invalid or incompatible
        """
        logger.info(f"ResumeEngine: Starting resume for job {job_id}")
        
        # Step 1: Load and validate
        state = await self._load_and_validate(job_id)
        logger.info(f"ResumeEngine: State loaded — project={state.project_id}, "
                     f"iteration={state.iteration_count}")
        
        # Step 2: Reconnect Git (if applicable)
        await self._reconnect_git(state)
        
        # Step 3: Rebuild StrategyEngine
        self._rebuild_strategy_engine(state)
        
        # Step 4: Determine resume point
        entry_node = self._determine_resume_point(state)
        logger.info(f"ResumeEngine: Resume entry point → {entry_node}")
        
        # Step 5: Verify filesystem
        await self._verify_filesystem(state)
        
        # Step 6: Mark state as resumed
        state.current_status = "resuming"
        if not hasattr(state, '_checkpoint_meta') or state._checkpoint_meta is None:
            state._checkpoint_meta = {}
        state._checkpoint_meta["resumed_at"] = datetime.now().isoformat()
        state._checkpoint_meta["resume_entry_node"] = entry_node
        
        return state, entry_node
    
    async def _load_and_validate(self, job_id: str) -> Any:
        """
        Load checkpoint and validate all required fields are present.
        
        Tries Redis first, falls back to filesystem.
        """
        from app.agents.state import AgentState
        
        # Attempt load
        state_dict = await self.checkpoint_mgr.load_state(job_id)
        
        if state_dict is None:
            raise ResumeValidationError(
                f"No checkpoint found for job_id '{job_id}'. "
                f"Available checkpoints can be listed via /api/checkpoints"
            )
        
        # Validate required fields
        missing = []
        for field_name in self.REQUIRED_FIELDS:
            if field_name not in state_dict:
                missing.append(field_name)
        
        if missing:
            raise ResumeValidationError(
                f"Checkpoint for '{job_id}' is missing required fields: {missing}. "
                f"This may be from an older, incompatible checkpoint format."
            )
        
        # Reconstruct AgentState from dict
        try:
            state = AgentState(**{
                k: v for k, v in state_dict.items() 
                if k in AgentState.__dataclass_fields__
            })
        except Exception as e:
            raise ResumeValidationError(
                f"Failed to reconstruct AgentState from checkpoint: {e}"
            )
        
        # Sanity checks
        if state.iteration_count < 0:
            state.iteration_count = 0
        if state.max_iterations <= 0:
            state.max_iterations = 3
        
        return state
    
    async def _reconnect_git(self, state: Any) -> None:
        """
        Verify Git repository state matches checkpoint expectations.
        
        Checks:
        1. Repo path exists on disk
        2. Current branch matches expected branch
        3. HEAD commit is reachable
        """
        if not state.repo_path:
            logger.info("ResumeEngine: No repo_path in state, skipping Git reconnection")
            return
        
        repo_path = Path(state.repo_path)
        
        if not repo_path.exists():
            logger.warning(
                f"ResumeEngine: Repo path {repo_path} does not exist on disk. "
                f"Git operations will be unavailable for this resume."
            )
            state.repo_path = None
            return
        
        # Verify .git directory exists
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            logger.warning(f"ResumeEngine: {repo_path} exists but has no .git directory")
            return
        
        # Verify branch
        try:
            import subprocess
            guard = SandboxGuard(project_root=str(repo_path))
            
            # Guard git rev-parse
            allowed, reason = guard.check_command("git rev-parse --abbrev-ref HEAD")
            if not allowed:
                logger.warning(f"ResumeEngine: SandboxGuard blocked git rev-parse: {reason}")
                return
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=10
            )
            current_branch = result.stdout.strip()
            
            expected_branch = state.current_branch or state.get("feature_branch", None)
            if expected_branch and current_branch != expected_branch:
                logger.warning(
                    f"ResumeEngine: Branch mismatch! "
                    f"Expected '{expected_branch}', found '{current_branch}'. "
                    f"Attempting checkout..."
                )
                # Guard git checkout
                checkout_cmd = f"git checkout {expected_branch}"
                allowed, reason = guard.check_command(checkout_cmd)
                if not allowed:
                    logger.error(f"ResumeEngine: SandboxGuard blocked git checkout: {reason}")
                    return
                checkout = subprocess.run(
                    ["git", "checkout", expected_branch],
                    cwd=str(repo_path), capture_output=True, text=True, timeout=15
                )
                if checkout.returncode != 0:
                    logger.error(f"ResumeEngine: Branch checkout failed: {checkout.stderr}")
                else:
                    logger.info(f"ResumeEngine: Successfully checked out {expected_branch}")
                    
        except Exception as e:
            logger.warning(f"ResumeEngine: Git verification failed: {e}")
    
    def _rebuild_strategy_engine(self, state: Any) -> None:
        """Rebuild StrategyEngine from serialized state if available."""
        if state.strategy_engine_state:
            from app.core.strategy_engine import StrategyEngine
            engine = StrategyEngine.from_dict(state.strategy_engine_state)
            logger.info(
                f"ResumeEngine: Restored StrategyEngine — "
                f"{engine.get_total_attempts()}/{engine.max_total_retries} attempts used, "
                f"history has {len(engine.history)} entries"
            )
        else:
            logger.info("ResumeEngine: No StrategyEngine state to restore, will create fresh")
    
    def _determine_resume_point(self, state: Any) -> str:
        """
        Determine which graph node to resume from.
        
        Strategy:
        1. If execution_plan exists → find first non-success step → map to node
        2. If no plan → infer from current_status
        3. Fallback → start from virtuoso (most common resume point)
        """
        # Strategy 1: Use execution plan step status
        if state.execution_plan:
            plan = state.execution_plan
            if hasattr(plan, 'steps') and plan.steps:
                for step in plan.steps:
                    if hasattr(step, 'status') and step.status != "success":
                        step_type = getattr(step, 'action', getattr(step, 'type', '')).lower()
                        node = STEP_TO_NODE.get(step_type)
                        if node:
                            logger.info(
                                f"ResumeEngine: Found incomplete step '{step_type}' "
                                f"(status={step.status}) → resuming at '{node}'"
                            )
                            if hasattr(step, 'step_id'):
                                state.current_step_id = step.step_id
                            return node
        
        # Strategy 2: Infer from current_status
        status = (state.current_status or "").lower()
        status_to_node = {
            "planning": "architect",
            "plan_ready": "virtuoso",
            "generating": "virtuoso",
            "validating": "sentinel",
            "testing": "testing",
            "reviewing": "advisor",
            "watching": "watcher",
            "fixing": "virtuoso",
            "deploying": "release",
            "resuming": "virtuoso",
        }
        
        node = status_to_node.get(status)
        if node:
            logger.info(f"ResumeEngine: Inferred entry from status '{status}' → '{node}'")
            return node
        
        # Strategy 3: Smart fallback based on what exists
        if state.file_system and len(state.file_system) > 0:
            # We have code, but errors → go to virtuoso for fixes
            if state.errors and len(state.errors) > 0:
                logger.info("ResumeEngine: Has files + errors → resuming at 'virtuoso'")
                return "virtuoso"
            else:
                # Code exists, no errors → run validation
                logger.info("ResumeEngine: Has files, no errors → resuming at 'sentinel'")
                return "sentinel"
        
        # No code at all → start from architect
        logger.info("ResumeEngine: No files generated yet → resuming at 'architect'")
        return "architect"
    
    async def _verify_filesystem(self, state: Any) -> None:
        """
        Verify that the on-disk filesystem matches what the checkpoint expects.
        
        Detects drift between checkpoint state and actual files.
        """
        if not state.project_id:
            return
        
        from app.core.filesystem import BASE_PROJECTS_DIR
        project_dir = Path(BASE_PROJECTS_DIR) / state.project_id
        
        if not project_dir.exists():
            if state.file_system and len(state.file_system) > 0:
                logger.warning(
                    f"ResumeEngine: Project dir {project_dir} doesn't exist "
                    f"but checkpoint has {len(state.file_system)} files. "
                    f"Files will be re-written from checkpoint state."
                )
                # Re-create project directory and write files
                project_dir.mkdir(parents=True, exist_ok=True)
                for rel_path, content in state.file_system.items():
                    file_path = project_dir / rel_path
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        file_path.write_text(
                            content if isinstance(content, str) else str(content),
                            encoding="utf-8"
                        )
                    except Exception as e:
                        logger.warning(f"ResumeEngine: Failed to restore {rel_path}: {e}")
            return
        
        # Check for major drift (files in checkpoint but missing on disk)
        if state.file_system:
            missing_count = 0
            for rel_path in list(state.file_system.keys())[:50]:  # Cap check
                full_path = project_dir / rel_path
                if not full_path.exists():
                    missing_count += 1
            
            total = len(state.file_system)
            if missing_count > 0:
                pct = (missing_count / total) * 100 if total > 0 else 0
                logger.warning(
                    f"ResumeEngine: Filesystem drift detected — "
                    f"{missing_count}/{total} files ({pct:.0f}%) missing from disk. "
                    f"Checkpoint state will be used as source of truth."
                )


# Singleton access
_resume_engine = None

def get_resume_engine() -> ResumeEngine:
    """Get singleton ResumeEngine."""
    global _resume_engine
    if _resume_engine is None:
        _resume_engine = ResumeEngine()
    return _resume_engine
