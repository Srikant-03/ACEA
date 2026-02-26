"""
Diagnostician Agent
Performs root-cause analysis on failures and recommends repair strategies.
"""

import logging
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class FailureCategory(str, Enum):
    """Types of failures."""
    SYNTAX_ERROR = "syntax_error"
    LOGIC_ERROR = "logic_error"
    IMPORT_ERROR = "import_error"
    TYPE_ERROR = "type_error"
    RUNTIME_ERROR = "runtime_error"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    NETWORK = "network"
    UI_LAYOUT = "ui_layout"
    UNKNOWN = "unknown"


class RepairStrategy(str, Enum):
    """Repair strategies."""
    TARGETED_FIX = "targeted_fix"        # Fix specific lines
    FULL_REWRITE = "full_rewrite"        # Regenerate entire file
    ADD_MISSING = "add_missing"          # Add missing imports/deps
    CONFIGURATION = "configuration"      # Fix config files
    ROLLBACK = "rollback"                # Revert to previous commit


class DiagnosticReport:
    """Root-cause analysis report."""
    
    def __init__(
        self,
        category: FailureCategory,
        root_cause: str,
        affected_files: List[str],
        recommended_strategy: RepairStrategy,
        fix_suggestions: List[str],
        confidence: float,
        reasoning: str
    ):
        self.category = category
        self.root_cause = root_cause
        self.affected_files = affected_files
        self.recommended_strategy = recommended_strategy
        self.fix_suggestions = fix_suggestions
        self.confidence = confidence
        self.reasoning = reasoning
    
    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "root_cause": self.root_cause,
            "affected_files": self.affected_files,
            "recommended_strategy": self.recommended_strategy.value,
            "fix_suggestions": self.fix_suggestions,
            "confidence": self.confidence,
            "reasoning": self.reasoning
        }


class DiagnosticianAgent:
    """
    Analyzes failures and suggests repair strategies.
    
    Uses:
    1. Error messages
    2. Stack traces
    3. Visual context (from Watcher)
    4. Thought signatures (from previous decisions)
    """
    
    def __init__(self):
        pass
    
    async def diagnose(
        self,
        errors: List[str],
        visual_context: Optional[Dict] = None,
        test_results: Optional[Dict] = None,
        thought_signatures: Optional[List] = None
    ) -> DiagnosticReport:
        """
        Perform root-cause analysis.
        
        Args:
            errors: List of error messages
            visual_context: From Watcher agent
            test_results: From Testing agent
            thought_signatures: Previous decision trail
            
        Returns:
            DiagnosticReport with recommendations
        """
        from app.core.local_model import HybridModelClient
        
        client = HybridModelClient()
        
        # Build diagnostic prompt
        prompt = self._build_diagnostic_prompt(
            errors, visual_context, test_results, thought_signatures
        )
        
        try:
            response = await client.generate(prompt, json_mode=True)
            
            from app.core.schema_validator import safe_parse_json, validate_diagnostic
            
            diagnosis, parse_error = safe_parse_json(response)
            if diagnosis is None:
                raise ValueError(f"Failed to parse diagnostic JSON: {parse_error}")
            
            # Validate against diagnostic schema
            diagnosis, warnings = validate_diagnostic(diagnosis)
            if diagnosis is None:
                raise ValueError(f"Diagnostic validation failed: {warnings}")
            if warnings:
                logger.warning(f"Diagnostic validated with {len(warnings)} warnings: {warnings[:3]}")
            
            return DiagnosticReport(
                category=FailureCategory(diagnosis.get("category", "unknown")),
                root_cause=diagnosis.get("root_cause", "Unknown"),
                affected_files=diagnosis.get("affected_files", []),
                recommended_strategy=RepairStrategy(
                    diagnosis.get("recommended_strategy", "targeted_fix")
                ),
                fix_suggestions=diagnosis.get("fix_suggestions", []),
                confidence=float(diagnosis.get("confidence", 0.5)),
                reasoning=diagnosis.get("reasoning", "")
            )
            
        except Exception as e:
            logger.error(f"Diagnosis failed: {e}")
            # Return conservative fallback
            return self._fallback_diagnosis(errors)
    
    def _build_diagnostic_prompt(
        self,
        errors: List[str],
        visual_context: Optional[Dict],
        test_results: Optional[Dict],
        thought_signatures: Optional[List]
    ) -> str:
        """Build Gemini prompt for diagnosis."""
        
        error_summary = "\n".join(f"- {e[:200]}" for e in errors[:5])
        
        visual_section = ""
        if visual_context:
            console_count = len(visual_context.get("console_errors", []))
            network_count = len(visual_context.get("network_failures", []))
            vision_quality = visual_context.get(
                "gemini_analysis", {}
            ).get("overall_quality", "N/A")
            visual_section = f"""
**Visual Context:**
- Console Errors: {console_count}
- Network Failures: {network_count}
- Gemini Vision: {vision_quality}
"""
        
        test_section = ""
        if test_results:
            test_section = f"""
**Test Results:**
- Failed: {test_results.get('failed', 0)}
- Passed: {test_results.get('passed', 0)}
"""

        sig_section = ""
        if thought_signatures:
            recent = thought_signatures[-3:]  # Last 3 decisions
            sig_lines = []
            for s in recent:
                if hasattr(s, "intent"):
                    sig_lines.append(
                        f"- [{s.agent}] {s.intent} (confidence: {s.confidence})"
                    )
                elif isinstance(s, dict):
                    sig_lines.append(
                        f"- [{s.get('agent', '?')}] {s.get('intent', '?')}"
                    )
            if sig_lines:
                sig_section = f"""
**Previous Decisions:**
{chr(10).join(sig_lines)}
"""
        
        return f"""You are an expert debugger analyzing code failures.

**ERRORS:**
{error_summary}
{visual_section}{test_section}{sig_section}
**YOUR TASK:**
Perform root-cause analysis and recommend repair strategy.

**OUTPUT FORMAT (JSON):**
{{{{
  "category": "syntax_error|logic_error|import_error|type_error|runtime_error|configuration|dependency|network|ui_layout|unknown",
  "root_cause": "Detailed explanation of underlying cause",
  "affected_files": ["file1.py", "file2.js"],
  "recommended_strategy": "targeted_fix|full_rewrite|add_missing|configuration|rollback",
  "fix_suggestions": [
    "Specific fix 1",
    "Specific fix 2"
  ],
  "confidence": 0.85,
  "reasoning": "Why this diagnosis and strategy"
}}}}

**CATEGORIES:**
- syntax_error: Code doesn't parse
- import_error: Missing imports or modules
- type_error: Type mismatches
- configuration: Wrong config (package.json, tsconfig, etc.)
- dependency: Missing npm/pip packages
- ui_layout: CSS/styling issues
- runtime_error: Crash at runtime
- logic_error: Wrong behavior
- network: API/fetch failures

**STRATEGIES:**
- targeted_fix: Fix specific lines (best for small, clear errors)
- full_rewrite: Regenerate file (for major logic issues)
- add_missing: Add imports/deps (for missing modules)
- configuration: Fix config files only
- rollback: Revert changes (only if too broken to fix)

Return ONLY JSON."""
    
    def _fallback_diagnosis(self, errors: List[str]) -> DiagnosticReport:
        """Conservative fallback when AI diagnosis fails."""
        first_error = errors[0] if errors else "Unknown error"
        lower = first_error.lower()
        
        category = FailureCategory.UNKNOWN
        strategy = RepairStrategy.TARGETED_FIX
        
        if "import" in lower or "module" in lower or "no module" in lower:
            category = FailureCategory.IMPORT_ERROR
            strategy = RepairStrategy.ADD_MISSING
        elif "syntax" in lower or "unexpected token" in lower:
            category = FailureCategory.SYNTAX_ERROR
            strategy = RepairStrategy.TARGETED_FIX
        elif "type" in lower or "typeerror" in lower:
            category = FailureCategory.TYPE_ERROR
            strategy = RepairStrategy.TARGETED_FIX
        elif "package.json" in lower or "config" in lower or "tsconfig" in lower:
            category = FailureCategory.CONFIGURATION
            strategy = RepairStrategy.CONFIGURATION
        elif "npm" in lower or "pip" in lower or "dependency" in lower:
            category = FailureCategory.DEPENDENCY
            strategy = RepairStrategy.ADD_MISSING
        elif "fetch" in lower or "network" in lower or "cors" in lower:
            category = FailureCategory.NETWORK
            strategy = RepairStrategy.TARGETED_FIX
        elif "css" in lower or "layout" in lower or "style" in lower:
            category = FailureCategory.UI_LAYOUT
            strategy = RepairStrategy.TARGETED_FIX
        
        return DiagnosticReport(
            category=category,
            root_cause=first_error[:200],
            affected_files=[],
            recommended_strategy=strategy,
            fix_suggestions=["Attempt targeted fix based on error message"],
            confidence=0.4,
            reasoning="Fallback heuristic diagnosis (AI unavailable)"
        )


# Factory function (replaces singleton for better testability)
def get_diagnostician() -> DiagnosticianAgent:
    """Create a new DiagnosticianAgent instance."""
    return DiagnosticianAgent()
