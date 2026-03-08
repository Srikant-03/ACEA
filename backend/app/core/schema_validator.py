"""
Schema Validator — Pydantic models for validating LLM JSON responses.

Each schema has a validate_or_fallback() class method that returns
validated data or a safe default with logged warnings.
"""

import logging
import json
import re
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  BLUEPRINT SCHEMA (Architect output)
# ─────────────────────────────────────────────────────────────

BLUEPRINT_REQUIRED_KEYS = {
    "project_name": str,
    "file_structure": list,
}

BLUEPRINT_OPTIONAL_KEYS = {
    "description": str,
    "project_type": str,
    "primary_stack": str,
    "rationale": str,
    "complexity": str,
    "tech_stack": (str, list),
    "api_endpoints": list,
    "security_policies": list,
    "thought_signature": dict,
}


def validate_blueprint(data: Any) -> Tuple[Optional[dict], List[str]]:
    """
    Validate architect blueprint output.
    
    Returns:
        (validated_data, warnings) — validated_data is None if fatally invalid.
    """
    warnings = []
    
    if not isinstance(data, dict):
        return None, ["Blueprint is not a dict"]
    
    # Check required keys
    for key, expected_type in BLUEPRINT_REQUIRED_KEYS.items():
        if key not in data:
            warnings.append(f"Missing required key: {key}")
            if key == "project_name":
                data["project_name"] = "unnamed_project"
            elif key == "file_structure":
                return None, [f"Fatal: missing '{key}'"]
        elif not isinstance(data[key], expected_type):
            warnings.append(f"Key '{key}' has wrong type: {type(data[key]).__name__}, expected {expected_type.__name__}")
    
    # Validate file_structure entries
    file_structure = data.get("file_structure", [])
    if isinstance(file_structure, list):
        valid_files = []
        for i, entry in enumerate(file_structure):
            if isinstance(entry, dict) and "path" in entry:
                valid_files.append(entry)
            elif isinstance(entry, str):
                valid_files.append({"path": entry, "description": ""})
                warnings.append(f"file_structure[{i}] was a string, converted to dict")
            else:
                warnings.append(f"file_structure[{i}] is invalid: {type(entry).__name__}")
        data["file_structure"] = valid_files
    
    # Validate optional keys types
    for key, expected_type in BLUEPRINT_OPTIONAL_KEYS.items():
        if key in data:
            if isinstance(expected_type, tuple):
                if not isinstance(data[key], expected_type):
                    warnings.append(f"Key '{key}' has unexpected type: {type(data[key]).__name__}")
            elif not isinstance(data[key], expected_type):
                warnings.append(f"Key '{key}' has unexpected type: {type(data[key]).__name__}")
    
    # Set defaults for optional fields
    data.setdefault("project_type", "dynamic")
    data.setdefault("primary_stack", "auto")
    data.setdefault("complexity", "simple")
    
    if warnings:
        logger.warning(f"Blueprint validation: {len(warnings)} warnings: {warnings[:3]}")
    
    return data, warnings


# ─────────────────────────────────────────────────────────────
#  GENERATED FILES SCHEMA (Virtuoso output)
# ─────────────────────────────────────────────────────────────

def validate_generated_files(data: Any) -> Tuple[Optional[dict], List[str]]:
    """
    Validate Virtuoso file generation output.
    
    Expects a dict of {filepath: content_string}.
    
    Returns:
        (validated_data, warnings) — validated_data is None if fatally invalid.
    """
    warnings = []
    
    if not isinstance(data, dict):
        return None, ["Generated files is not a dict"]
    
    if len(data) == 0:
        return None, ["Generated files dict is empty"]
    
    validated = {}
    for path, content in data.items():
        # Skip metadata keys
        if path.startswith("__"):
            continue
        
        if not isinstance(path, str) or not path.strip():
            warnings.append(f"Invalid file path: {repr(path)}")
            continue
        
        if content is None:
            warnings.append(f"File '{path}' has None content, using empty string")
            content = ""
        
        if not isinstance(content, str):
            if isinstance(content, dict):
                if path.endswith(".json"):
                    content = json.dumps(content, indent=2)
                    warnings.append(f"File '{path}' content was a dict, serialized to JSON")
                else:
                    warnings.append(f"File '{path}' content is a dict (not str), skipping")
                    continue
            else:
                content = str(content)
                warnings.append(f"File '{path}' content was {type(content).__name__}, cast to str")
        
        validated[path] = content
    
    if len(validated) == 0:
        return None, warnings + ["No valid files after validation"]
    
    if warnings:
        logger.warning(f"Generated files validation: {len(warnings)} warnings")
    
    return validated, warnings


# ─────────────────────────────────────────────────────────────
#  DIAGNOSTIC SCHEMA (Diagnostician output)
# ─────────────────────────────────────────────────────────────

VALID_CATEGORIES = {
    "syntax_error", "logic_error", "import_error", "type_error",
    "runtime_error", "configuration", "dependency", "network",
    "ui_layout", "unknown",
}

VALID_STRATEGIES = {
    "targeted_fix", "full_rewrite", "add_missing",
    "configuration", "rollback",
}


def validate_diagnostic(data: Any) -> Tuple[Optional[dict], List[str]]:
    """
    Validate Diagnostician output.
    
    Returns:
        (validated_data, warnings) — validated_data uses safe defaults for invalid fields.
    """
    warnings = []
    
    if not isinstance(data, dict):
        return None, ["Diagnostic output is not a dict"]
    
    # Validate and fix category
    category = data.get("category", "unknown")
    if category not in VALID_CATEGORIES:
        warnings.append(f"Invalid category '{category}', defaulting to 'unknown'")
        data["category"] = "unknown"
    
    # Validate and fix strategy
    strategy = data.get("recommended_strategy", "targeted_fix")
    if strategy not in VALID_STRATEGIES:
        warnings.append(f"Invalid strategy '{strategy}', defaulting to 'targeted_fix'")
        data["recommended_strategy"] = "targeted_fix"
    
    # Ensure required fields exist
    data.setdefault("root_cause", "Unknown")
    data.setdefault("affected_files", [])
    data.setdefault("fix_suggestions", [])
    data.setdefault("confidence", 0.5)
    data.setdefault("reasoning", "")
    
    # Validate types
    if not isinstance(data["affected_files"], list):
        data["affected_files"] = []
        warnings.append("affected_files was not a list, reset to empty")
    
    if not isinstance(data["fix_suggestions"], list):
        data["fix_suggestions"] = [str(data["fix_suggestions"])]
        warnings.append("fix_suggestions was not a list, wrapped in list")
    
    try:
        data["confidence"] = float(data["confidence"])
        data["confidence"] = max(0.0, min(1.0, data["confidence"]))
    except (ValueError, TypeError):
        data["confidence"] = 0.5
        warnings.append("confidence was not a valid float, defaulting to 0.5")
    
    if warnings:
        logger.warning(f"Diagnostic validation: {len(warnings)} warnings")
    
    return data, warnings


# ─────────────────────────────────────────────────────────────
#  PLAN SCHEMA (Planner output)
# ─────────────────────────────────────────────────────────────

VALID_ACTIONS = {"create", "modify", "delete", "test", "verify", "commit"}
VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}


def validate_plan(data: Any) -> Tuple[Optional[dict], List[str]]:
    """
    Validate Planner output.
    
    Returns:
        (validated_data, warnings) — validated_data is None if fatally invalid.
    """
    warnings = []
    
    if not isinstance(data, dict):
        return None, ["Plan output is not a dict"]
    
    data.setdefault("strategy", "AI Generated Strategy")
    data.setdefault("risk_assessment", "Low")
    data.setdefault("total_estimated_tokens", 0)
    data.setdefault("estimated_duration_minutes", 10)
    
    steps = data.get("steps", [])
    if not isinstance(steps, list):
        return None, ["Plan 'steps' is not a list"]
    
    validated_steps = []
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            warnings.append(f"Step {i} is not a dict, skipping")
            continue
        
        # Validate action
        action = step.get("action", "modify")
        if action not in VALID_ACTIONS:
            warnings.append(f"Step {i}: invalid action '{action}', defaulting to 'modify'")
            step["action"] = "modify"
        
        # Validate risk_level
        risk = step.get("risk_level", "low")
        if risk not in VALID_RISK_LEVELS:
            warnings.append(f"Step {i}: invalid risk_level '{risk}', defaulting to 'low'")
            step["risk_level"] = "low"
        
        # Ensure required fields
        step.setdefault("id", f"s{i+1}")
        step.setdefault("intent", "")
        step.setdefault("target_files", [])
        step.setdefault("dependencies", [])
        step.setdefault("verification_method", "Manual review")
        step.setdefault("estimated_tokens", 500)
        step.setdefault("rationale", "")
        step.setdefault("rollback_strategy", "git reset")
        
        validated_steps.append(step)
    
    data["steps"] = validated_steps
    
    if warnings:
        logger.warning(f"Plan validation: {len(warnings)} warnings")
    
    return data, warnings


# ─────────────────────────────────────────────────────────────
#  GENERIC JSON PARSING HELPER
# ─────────────────────────────────────────────────────────────

def safe_parse_json(raw: str) -> Tuple[Optional[dict], Optional[str]]:
    """
    Multi-stage JSON parser (extracted from Virtuoso for reuse).
    
    Stages:
    1. Direct json.loads
    2. Strip markdown fences + retry
    3. Fix trailing commas + retry
    
    Returns:
        (parsed_dict, error_message)
    """
    if not raw or not raw.strip():
        return None, "Empty input"
    
    # Stage 1: Direct parse
    stage1_error = "JSON parsed successfully but result was not a dict"
    try:
        result = json.loads(raw, strict=False)
        if isinstance(result, dict):
            return result, None
        # If we get here, JSON is valid but not a dict (e.g., array)
        stage1_error = f"JSON parsed as {type(result).__name__}, expected dict"
    except json.JSONDecodeError as e:
        stage1_error = str(e)
    
    # Stage 2: Strip markdown fences and extract JSON object
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "```":
                lines = lines[:i]
                break
        cleaned = "\n".join(lines)
    
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace:last_brace + 1]
    
    try:
        result = json.loads(cleaned, strict=False)
        if isinstance(result, dict):
            return result, None
    except json.JSONDecodeError:
        pass
    
    # Stage 3: Fix trailing commas
    fixed = re.sub(r',\s*([}\]])', r'\1', cleaned)
    try:
        result = json.loads(fixed, strict=False)
        if isinstance(result, dict):
            return result, None
    except json.JSONDecodeError:
        pass
    
    # Split off THOUGHT_SIGNATURE if present
    if "THOUGHT_SIGNATURE:" in cleaned:
        json_part = cleaned.split("THOUGHT_SIGNATURE:")[0].strip()
        try:
            result = json.loads(json_part, strict=False)
            if isinstance(result, dict):
                return result, None
        except json.JSONDecodeError:
            pass
    
    return None, stage1_error
