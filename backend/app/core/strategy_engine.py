"""
Strategy Engine — Intelligent Repair Strategy Selection with Memory & Escalation

Transforms ACEA's blind retry loop into a stateful decision engine that:
1. Tracks what strategies have been attempted and their outcomes
2. Enforces per-strategy retry limits
3. Escalates through increasingly aggressive strategies
4. Knows when to halt (budget exhausted)
5. Provides serializable history for checkpointing

Escalation ladder (most conservative → most aggressive):
  TARGETED_FIX (2 attempts) → ADD_MISSING (1) → CONFIGURATION (1) → FULL_REWRITE (1) → ROLLBACK (terminal)
"""

import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RepairStrategy(str, Enum):
    """Mirror of diagnostician.RepairStrategy for decoupled imports."""
    TARGETED_FIX = "targeted_fix"
    ADD_MISSING = "add_missing"
    CONFIGURATION = "configuration"
    FULL_REWRITE = "full_rewrite"
    ROLLBACK = "rollback"


@dataclass
class StrategyAttempt:
    """Records a single repair attempt for audit and decision-making."""
    strategy: str
    attempt_number: int
    timestamp: str
    errors_before: List[str]
    errors_after: List[str]
    success: bool
    error_delta: int  # negative = improvement, positive = regression
    duration_ms: int = 0
    diagnosis_summary: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: dict) -> "StrategyAttempt":
        return cls(**d)


class StrategyEngine:
    """
    Stateful strategy selector with memory, escalation, and budget enforcement.
    
    The engine maintains a history of all repair attempts and uses it to make
    intelligent decisions about which strategy to try next. It prevents
    repeating strategies that have already failed at their retry limit.
    
    Usage:
        engine = StrategyEngine(max_total_retries=5)
        strategy = engine.select_strategy(diagnosis)
        # ... execute repair ...
        engine.record_attempt(strategy, success=False, 
                              errors_before=[...], errors_after=[...])
    """
    
    # Escalation ladder: (strategy, max_attempts_for_this_strategy)
    ESCALATION_ORDER: List[Tuple[RepairStrategy, int]] = [
        (RepairStrategy.TARGETED_FIX, 2),
        (RepairStrategy.ADD_MISSING, 1),
        (RepairStrategy.CONFIGURATION, 1),
        (RepairStrategy.FULL_REWRITE, 1),
        (RepairStrategy.ROLLBACK, 1),  # terminal — no further escalation
    ]
    
    def __init__(self, max_total_retries: int = 5):
        self.max_total_retries = max_total_retries
        self.history: List[StrategyAttempt] = []
        self._strategy_counts: Dict[str, int] = {}
        self._halted = False
    
    def select_strategy(
        self,
        diagnosis_recommendation: Optional[str] = None,
        error_fingerprints: Optional[List[str]] = None
    ) -> RepairStrategy:
        """
        Select the best repair strategy based on history and diagnosis.
        
        Logic:
        1. If budget exhausted → ROLLBACK
        2. If diagnosis recommends a strategy AND it hasn't exceeded its limit → use it
        3. Otherwise → find the next strategy in the escalation ladder that has budget
        4. If all strategies exhausted → ROLLBACK (terminal)
        
        Args:
            diagnosis_recommendation: Strategy recommended by DiagnosticianAgent
            error_fingerprints: Hashed error signatures for dedup detection
            
        Returns:
            The selected RepairStrategy
        """
        if self.should_halt():
            logger.warning("StrategyEngine: Budget exhausted, forcing ROLLBACK")
            return RepairStrategy.ROLLBACK
        
        # Check if diagnosis recommendation has budget remaining
        if diagnosis_recommendation:
            try:
                recommended = RepairStrategy(diagnosis_recommendation)
                max_for_strategy = self._get_max_attempts(recommended)
                used = self._strategy_counts.get(recommended.value, 0)
                
                if used < max_for_strategy:
                    logger.info(
                        f"StrategyEngine: Using diagnosed strategy "
                        f"{recommended.value} ({used}/{max_for_strategy} used)"
                    )
                    return recommended
                else:
                    logger.info(
                        f"StrategyEngine: Diagnosed strategy {recommended.value} "
                        f"exhausted ({used}/{max_for_strategy}), escalating..."
                    )
            except ValueError:
                logger.warning(f"StrategyEngine: Unknown strategy '{diagnosis_recommendation}'")
        
        # Detect stuck-in-loop: if last 2 attempts used the same strategy 
        # and errors didn't improve, force escalation
        if len(self.history) >= 2:
            last_two = self.history[-2:]
            if (last_two[0].strategy == last_two[1].strategy 
                    and last_two[1].error_delta >= 0):
                logger.info(
                    f"StrategyEngine: Detected stall on {last_two[0].strategy}, "
                    f"forcing escalation past it"
                )
                # Mark this strategy as fully exhausted
                stalled_strategy = last_two[0].strategy
                max_for_it = self._get_max_attempts(RepairStrategy(stalled_strategy))
                self._strategy_counts[stalled_strategy] = max_for_it
        
        # Escalation: find next strategy with remaining budget
        for strategy, max_attempts in self.ESCALATION_ORDER:
            used = self._strategy_counts.get(strategy.value, 0)
            if used < max_attempts:
                logger.info(
                    f"StrategyEngine: Escalating to {strategy.value} "
                    f"({used}/{max_attempts} used)"
                )
                return strategy
        
        # All strategies exhausted
        logger.warning("StrategyEngine: All strategies exhausted, terminal ROLLBACK")
        self._halted = True
        return RepairStrategy.ROLLBACK
    
    def record_attempt(
        self,
        strategy: RepairStrategy,
        success: bool,
        errors_before: List[str],
        errors_after: List[str],
        duration_ms: int = 0,
        diagnosis_summary: str = ""
    ) -> StrategyAttempt:
        """
        Record the outcome of a repair attempt.
        
        Updates internal counters and history for future strategy selection.
        """
        attempt_num = self._strategy_counts.get(strategy.value, 0) + 1
        self._strategy_counts[strategy.value] = attempt_num
        
        error_delta = len(errors_after) - len(errors_before)
        
        attempt = StrategyAttempt(
            strategy=strategy.value,
            attempt_number=attempt_num,
            timestamp=datetime.now().isoformat(),
            errors_before=errors_before[:10],  # Cap for serialization
            errors_after=errors_after[:10],
            success=success,
            error_delta=error_delta,
            duration_ms=duration_ms,
            diagnosis_summary=diagnosis_summary[:200]
        )
        
        self.history.append(attempt)
        
        log_fn = logger.info if success else logger.warning
        log_fn(
            f"StrategyEngine: {strategy.value} attempt #{attempt_num} "
            f"{'SUCCESS' if success else 'FAILED'} "
            f"(errors: {len(errors_before)} → {len(errors_after)}, "
            f"delta: {error_delta:+d})"
        )
        
        return attempt
    
    def should_halt(self) -> bool:
        """Check if retry budget is exhausted."""
        total_attempts = sum(self._strategy_counts.values())
        return self._halted or total_attempts >= self.max_total_retries
    
    def get_total_attempts(self) -> int:
        """Get total number of retry attempts used."""
        return sum(self._strategy_counts.values())
    
    def get_summary(self) -> dict:
        """Serializable summary for artifacts and checkpointing."""
        return {
            "total_attempts": self.get_total_attempts(),
            "max_total_retries": self.max_total_retries,
            "budget_remaining": max(0, self.max_total_retries - self.get_total_attempts()),
            "halted": self._halted,
            "strategy_counts": dict(self._strategy_counts),
            "history": [a.to_dict() for a in self.history],
            "escalation_path": [
                {"strategy": s.value, "max": m, "used": self._strategy_counts.get(s.value, 0)}
                for s, m in self.ESCALATION_ORDER
            ]
        }
    
    def _get_max_attempts(self, strategy: RepairStrategy) -> int:
        """Get the max allowed attempts for a given strategy."""
        for s, max_a in self.ESCALATION_ORDER:
            if s == strategy:
                return max_a
        return 1  # Default
    
    # --- Serialization for checkpoint persistence ---
    
    def to_dict(self) -> dict:
        """Serialize engine state for checkpointing."""
        return {
            "max_total_retries": self.max_total_retries,
            "strategy_counts": dict(self._strategy_counts),
            "halted": self._halted,
            "history": [a.to_dict() for a in self.history]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "StrategyEngine":
        """Restore engine from checkpoint data."""
        engine = cls(max_total_retries=data.get("max_total_retries", 5))
        engine._strategy_counts = data.get("strategy_counts", {})
        engine._halted = data.get("halted", False)
        engine.history = [
            StrategyAttempt.from_dict(a) for a in data.get("history", [])
        ]
        return engine
