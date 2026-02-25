"""
Sandbox Guard — Command & File Access Policy Enforcement

Enforces strict rules for what commands can be run and what files can be accessed
within sandboxed environments. Critical for production safety when the agent
executes arbitrary code in E2B or local environments.

Policy:
- ALLOWLIST-based command execution (only whitelisted commands run)
- Path jail: no access outside project directory
- Rate limiting: caps commands per minute
- Audit trail: logs every allowed/denied action
"""

import re
import logging
import time
from typing import List, Optional, Set, Tuple, Dict
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)


class SandboxGuard:
    """
    Enforces command and filesystem access policies.
    
    Usage:
        guard = SandboxGuard(project_root="/home/user/myproject")
        allowed, reason = guard.check_command("npm install")
        allowed, reason = guard.check_file_access("/home/user/myproject/src/index.js")
    """
    
    # Allowed command prefixes (binary names)
    ALLOWED_COMMANDS: Set[str] = {
        # Package managers
        "npm", "npx", "yarn", "pnpm", "pip", "pip3", "poetry",
        # Build tools
        "node", "python", "python3", "tsc", "vite", "webpack", "esbuild",
        # Test runners
        "pytest", "jest", "vitest", "mocha", "cypress",
        # Language-specific tools (Ruby, Rust, PHP, .NET, C++)
        "bundle", "rails", "ruby", "gem",
        "cargo", "rustc",
        "composer", "php",
        "dotnet",
        "cmake", "make", "gcc", "g++",
        # Linters / formatters
        "eslint", "prettier", "black", "ruff", "flake8", "mypy",
        # Security scanners
        "bandit", "semgrep",
        # Git (read-only subset)
        "git",
        # File operations (safe subset)
        "cat", "ls", "find", "head", "tail", "wc", "grep", "echo",
        "mkdir", "cp", "mv", "touch",
        # Process management
        "kill", "lsof",
    }
    
    # Explicitly blocked commands (override allowlist)
    BLOCKED_COMMANDS: Set[str] = {
        "rm", "rmdir", "dd", "mkfs", "fdisk", "format",
        "shutdown", "reboot", "halt", "poweroff",
        "curl", "wget", "ssh", "scp", "rsync", "nc", "netcat",
        "sudo", "su", "chmod", "chown", "chgrp",
        "eval", "exec", "source",
    }
    
    # Blocked patterns (regex)
    BLOCKED_PATTERNS: List[str] = [
        r"rm\s+-rf\s+/",         # rm -rf /
        r"\.\./\.\./",          # Path traversal
        r";\s*(rm|dd|curl|wget|sudo)",  # Command injection
        r"\|\s*(sh|bash|zsh)",  # Pipe to shell
        r"`.*`",                # Backtick command substitution
        r"\$\(.*\)",            # $() command substitution
        r">\s*/dev",            # Redirect to /dev
        r">\s*/etc",            # Redirect to /etc
        r">\s*/proc",           # Redirect to /proc
    ]
    
    # Git subcommands allowed (read-heavy + commit/branch for ACEA workflow)
    ALLOWED_GIT_SUBCOMMANDS: Set[str] = {
        "status", "log", "diff", "show", "branch", "checkout", 
        "add", "commit", "tag", "rev-parse", "remote", "fetch",
        "stash", "reset", "init", "clone",
    }
    
    # Dangerous git subcommands
    BLOCKED_GIT_SUBCOMMANDS: Set[str] = {
        "push", "pull", "rebase", "merge", "cherry-pick",
        "gc", "prune", "reflog",
    }
    
    def __init__(
        self,
        project_root: str,
        max_commands_per_minute: int = 30,
        allow_network: bool = False
    ):
        self.project_root = Path(project_root).resolve()
        self.max_commands_per_minute = max_commands_per_minute
        self.allow_network = allow_network
        
        # Rate limiting
        self._command_timestamps: List[float] = []
        
        # Audit trail
        self.audit_log: List[Dict] = []
    
    def check_command(self, command: str) -> Tuple[bool, str]:
        """
        Check if a command is allowed to execute.
        
        Returns:
            (allowed, reason)
        """
        command = command.strip()
        if not command:
            return (False, "Empty command")
        
        # Rate limit check
        if not self._check_rate_limit():
            reason = f"Rate limit exceeded ({self.max_commands_per_minute}/min)"
            self._audit("DENIED_RATE_LIMIT", command, reason)
            return (False, reason)
        
        # Extract base command
        parts = command.split()
        base_cmd = parts[0].lower()
        
        # Strip path prefix (e.g., /usr/bin/python → python)
        base_cmd = base_cmd.split("/")[-1].split("\\")[-1]
        
        # Check blocked commands first (highest priority)
        if base_cmd in self.BLOCKED_COMMANDS:
            reason = f"Command '{base_cmd}' is explicitly blocked"
            self._audit("DENIED_BLOCKED", command, reason)
            return (False, reason)
        
        # Check blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Command matches blocked pattern: {pattern}"
                self._audit("DENIED_PATTERN", command, reason)
                return (False, reason)
        
        # Check if command is in allowlist
        if base_cmd not in self.ALLOWED_COMMANDS:
            reason = f"Command '{base_cmd}' not in allowlist"
            self._audit("DENIED_NOT_ALLOWED", command, reason)
            return (False, reason)
        
        # Special handling for git
        if base_cmd == "git" and len(parts) > 1:
            git_subcmd = parts[1].lower()
            if git_subcmd in self.BLOCKED_GIT_SUBCOMMANDS:
                reason = f"Git subcommand '{git_subcmd}' is blocked"
                self._audit("DENIED_GIT", command, reason)
                return (False, reason)
            if git_subcmd not in self.ALLOWED_GIT_SUBCOMMANDS:
                reason = f"Git subcommand '{git_subcmd}' not in allowlist"
                self._audit("DENIED_GIT", command, reason)
                return (False, reason)
        
        # Network check: block commands that imply network access
        if not self.allow_network:
            network_indicators = ["--registry", "https://", "http://", "@latest"]
            # npm install is allowed (local packages), but explicit registry URLs are blocked
            if any(indicator in command for indicator in ["https://", "http://"]):
                if base_cmd not in ("npm", "npx", "yarn", "pip", "pip3"):
                    reason = "Network access not allowed in sandbox"
                    self._audit("DENIED_NETWORK", command, reason)
                    return (False, reason)
        
        self._audit("ALLOWED", command)
        return (True, "OK")
    
    def check_file_access(
        self,
        file_path: str,
        write: bool = False
    ) -> Tuple[bool, str]:
        """
        Check if accessing a file path is allowed (path jail).
        
        Args:
            file_path: Path to check
            write: Whether this is a write operation
            
        Returns:
            (allowed, reason)
        """
        try:
            resolved = Path(file_path).resolve()
        except Exception as e:
            return (False, f"Invalid path: {e}")
        
        # Must be within project root
        try:
            resolved.relative_to(self.project_root)
        except ValueError:
            reason = (
                f"Path '{file_path}' is outside project root "
                f"'{self.project_root}'"
            )
            self._audit("DENIED_PATH_JAIL", str(file_path), reason)
            return (False, reason)
        
        # Block access to sensitive files (even within project root)
        sensitive_patterns = [
            ".env", ".env.local", ".env.production",
            "id_rsa", "id_ed25519", ".pem", ".key",
            ".git/config", "credentials",
        ]
        
        path_str = str(resolved).lower()
        for pattern in sensitive_patterns:
            if pattern in path_str and write:
                reason = f"Write access to sensitive file '{pattern}' is blocked"
                self._audit("DENIED_SENSITIVE", str(file_path), reason)
                return (False, reason)
        
        self._audit("ALLOWED_FILE", str(file_path))
        return (True, "OK")
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        window_start = now - 60  # 1-minute window
        
        # Remove old timestamps
        self._command_timestamps = [
            t for t in self._command_timestamps if t > window_start
        ]
        
        if len(self._command_timestamps) >= self.max_commands_per_minute:
            return False
        
        self._command_timestamps.append(now)
        return True
    
    def _audit(self, action: str, command: str, reason: str = ""):
        """Record audit entry."""
        entry = {
            "timestamp": time.time(),
            "action": action,
            "command": command[:200],
            "reason": reason[:200]
        }
        self.audit_log.append(entry)
        
        # Keep audit log bounded
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-500:]
        
        # Log denials
        if "DENIED" in action:
            logger.warning(f"SandboxGuard: {action} — {command[:100]} — {reason}")
    
    def get_audit_summary(self) -> Dict:
        """Get summary of audit activity."""
        total = len(self.audit_log)
        allowed = sum(1 for e in self.audit_log if e["action"].startswith("ALLOWED"))
        denied = total - allowed
        
        return {
            "total_checks": total,
            "allowed": allowed,
            "denied": denied,
            "denial_rate": f"{(denied/total*100):.1f}%" if total > 0 else "0%",
            "recent_denials": [
                e for e in self.audit_log[-10:] if "DENIED" in e["action"]
            ]
        }


# Singleton
_guard = None

def get_sandbox_guard(project_root: str = None) -> SandboxGuard:
    """Get or create SandboxGuard."""
    global _guard
    if _guard is None:
        if project_root is None:
            project_root = "."
        _guard = SandboxGuard(project_root)
    return _guard
