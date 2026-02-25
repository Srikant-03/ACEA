"""
Input Sanitizer — Defense against prompt injection and input abuse.

Wraps user-provided text so LLMs treat it as data, not executable instructions.
Also filters known injection patterns and validates prompt length.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Known prompt injection patterns (case-insensitive)
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"you\s+are\s+now\s+a",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"<\s*system\s*>",
    r"```\s*system",
    r"ADMIN\s*OVERRIDE",
    r"SUDO\s+MODE",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode\s+enabled",
]

# Compiled regex for efficiency
_INJECTION_RE = re.compile(
    "|".join(f"({p})" for p in INJECTION_PATTERNS),
    re.IGNORECASE
)

# Max reasonable prompt length (characters)
DEFAULT_MAX_PROMPT_LENGTH = 10000


def sanitize_user_prompt(text: str, max_length: int = DEFAULT_MAX_PROMPT_LENGTH) -> str:
    """
    Sanitize user prompt:
    1. Strip leading/trailing whitespace
    2. Truncate to max_length
    3. Flag (but don't silently drop) injection patterns
    
    Returns the cleaned text. Logs warnings for flagged patterns.
    """
    if not text:
        return ""
    
    # Strip whitespace
    cleaned = text.strip()
    
    # Truncate
    if len(cleaned) > max_length:
        logger.warning(
            f"User prompt truncated from {len(cleaned)} to {max_length} chars"
        )
        cleaned = cleaned[:max_length]
    
    # Check for injection patterns
    matches = _INJECTION_RE.findall(cleaned)
    if matches:
        # Flatten the tuple groups from findall
        found_patterns = [m for group in matches for m in group if m]
        logger.warning(
            f"Potential prompt injection detected: {found_patterns[:3]}. "
            f"Input will be isolated in USER_INPUT envelope."
        )
    
    return cleaned


def wrap_user_input(text: str) -> str:
    """
    Wrap user-provided text in a clear envelope so the LLM treats it as
    data, not executable instructions.
    
    This is the primary defense against prompt injection — the system prompt
    instructs the model that content within USER_INPUT tags is untrusted data.
    """
    sanitized = sanitize_user_prompt(text)
    return f'<USER_INPUT>\n{sanitized}\n</USER_INPUT>'


def validate_prompt_length(
    text: str,
    max_chars: int = DEFAULT_MAX_PROMPT_LENGTH
) -> tuple:
    """
    Validate prompt length.
    
    Returns:
        (is_valid: bool, message: str)
    """
    if not text or not text.strip():
        return False, "Prompt cannot be empty"
    
    if len(text.strip()) > max_chars:
        return False, f"Prompt too long ({len(text.strip())} chars, max {max_chars})"
    
    if len(text.strip()) < 3:
        return False, "Prompt too short (minimum 3 characters)"
    
    return True, "OK"


def escape_for_prompt(text: str) -> str:
    """
    Escape special characters that could confuse prompt parsing.
    Useful for embedding file contents or error messages in prompts.
    """
    # Escape curly braces (prevent f-string/template injection)
    escaped = text.replace("{", "{{").replace("}", "}}")
    return escaped
