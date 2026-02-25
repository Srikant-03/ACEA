"""
Git Operations Adapter
Handles repository cloning, branching, commits, and rollback.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime
import git
from git import Repo, GitCommandError

logger = logging.getLogger(__name__)


class GitAdapter:
    """
    Manages Git operations for ACEA autonomous workflows.
    
    Responsibilities:
    - Clone external repositories
    - Create feature branches
    - Commit changes with context
    - Generate diffs for artifacts
    - Rollback on failures
    """
    
    def __init__(self, workspace_dir: str = "/tmp/acea_repos"):
        """
        Initialize Git adapter.
        
        Args:
            workspace_dir: Directory for cloning repos
        """
        self.workspace_dir = Path(workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.repos: Dict[str, Repo] = {}  # project_id -> Repo
        
    def clone_repository(
        self,
        project_id: str,
        repo_url: str,
        branch: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Clone a Git repository.
        
        Args:
            project_id: Unique project identifier
            repo_url: Git repository URL
            branch: Optional branch to checkout
            
        Returns:
            (success, message, repo_path)
        """
        repo_path = self.workspace_dir / project_id
        
        try:
            # Remove existing if present
            if repo_path.exists():
                import shutil
                shutil.rmtree(repo_path)
            
            logger.info(f"Cloning {repo_url} to {repo_path}")
            
            # Clone with depth=1 for speed
            repo = Repo.clone_from(
                repo_url,
                repo_path,
                branch=branch,
                depth=1
            )
            
            self.repos[project_id] = repo
            
            return (
                True,
                f"Successfully cloned {repo_url}",
                str(repo_path)
            )
            
        except GitCommandError as e:
            logger.error(f"Failed to clone {repo_url}: {e}")
            return (False, f"Clone failed: {str(e)}", None)
        except Exception as e:
            logger.error(f"Unexpected error cloning {repo_url}: {e}")
            return (False, f"Error: {str(e)}", None)
    
    def create_feature_branch(
        self,
        project_id: str,
        branch_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Create and checkout a new feature branch.
        
        Args:
            project_id: Project identifier
            branch_name: Branch name (auto-generated if None)
            
        Returns:
            (success, message)
        """
        repo = self.repos.get(project_id)
        if not repo:
            return (False, f"No repo found for project {project_id}")
        
        try:
            if not branch_name:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                branch_name = f"acea/auto_{timestamp}"
            
            # Create new branch from current HEAD
            new_branch = repo.create_head(branch_name)
            new_branch.checkout()
            
            logger.info(f"Created and checked out branch: {branch_name}")
            return (True, f"Branch '{branch_name}' created")
            
        except GitCommandError as e:
            logger.error(f"Failed to create branch: {e}")
            return (False, f"Branch creation failed: {str(e)}")
    
    def commit_changes(
        self,
        project_id: str,
        message: str,
        file_patterns: Optional[List[str]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Commit changes to repository.
        
        Args:
            project_id: Project identifier
            message: Commit message
            file_patterns: Specific files to commit (None = all)
            
        Returns:
            (success, message, commit_sha)
        """
        repo = self.repos.get(project_id)
        if not repo:
            return (False, f"No repo found for project {project_id}", None)
        
        try:
            # Stage changes
            if file_patterns:
                for pattern in file_patterns:
                    repo.index.add([pattern])
            else:
                repo.git.add(A=True)  # Add all changes
            
            # Check if there are changes to commit
            if not repo.index.diff("HEAD") and not repo.untracked_files:
                return (True, "No changes to commit", None)
            
            # Commit
            commit = repo.index.commit(message)
            commit_sha = commit.hexsha[:8]
            
            logger.info(f"Committed changes: {commit_sha} - {message}")
            return (True, f"Committed: {commit_sha}", commit_sha)
            
        except GitCommandError as e:
            logger.error(f"Failed to commit: {e}")
            return (False, f"Commit failed: {str(e)}", None)
    
    def rollback_to_commit(
        self,
        project_id: str,
        commit_sha: str
    ) -> Tuple[bool, str]:
        """
        Hard reset to a specific commit.
        
        Args:
            project_id: Project identifier
            commit_sha: Commit to reset to
            
        Returns:
            (success, message)
        """
        repo = self.repos.get(project_id)
        if not repo:
            return (False, f"No repo found for project {project_id}")
        
        try:
            repo.git.reset('--hard', commit_sha)
            logger.info(f"Rolled back to commit: {commit_sha}")
            return (True, f"Rolled back to {commit_sha}")
            
        except GitCommandError as e:
            logger.error(f"Rollback failed: {e}")
            return (False, f"Rollback failed: {str(e)}")
    
    def get_diff(
        self,
        project_id: str,
        from_commit: Optional[str] = None,
        to_commit: str = "HEAD"
    ) -> Optional[str]:
        """
        Get diff between commits.
        
        Args:
            project_id: Project identifier
            from_commit: Starting commit (None = working dir vs HEAD)
            to_commit: Ending commit
            
        Returns:
            Diff as string or None
        """
        repo = self.repos.get(project_id)
        if not repo:
            return None
        
        try:
            if from_commit:
                diff = repo.git.diff(from_commit, to_commit)
            else:
                diff = repo.git.diff(to_commit)
            
            return diff
            
        except GitCommandError as e:
            logger.error(f"Failed to get diff: {e}")
            return None
    
    def analyze_repository(self, project_id: str) -> Dict[str, any]:
        """
        Analyze repository structure and files.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Analysis dict with file counts, languages, etc.
        """
        repo = self.repos.get(project_id)
        if not repo:
            return {"error": "Repository not found"}
        
        repo_path = Path(repo.working_dir)
        
        # Count files by extension
        file_counts = {}
        total_lines = 0
        
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self._should_ignore(file_path):
                ext = file_path.suffix or "no_extension"
                file_counts[ext] = file_counts.get(ext, 0) + 1
                
                # Count lines for text files
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        total_lines += len(f.readlines())
                except:
                    pass  # Skip binary files
        
        # Detect primary languages
        language_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript',
            '.jsx': 'JavaScript',
            '.java': 'Java',
            '.go': 'Go',
            '.rs': 'Rust',
            '.cpp': 'C++',
            '.c': 'C',
        }
        
        languages = {}
        for ext, count in file_counts.items():
            if ext in language_map:
                lang = language_map[ext]
                languages[lang] = languages.get(lang, 0) + count
        
        return {
            "total_files": sum(file_counts.values()),
            "total_lines": total_lines,
            "file_types": file_counts,
            "primary_languages": languages,
            "repository_path": str(repo_path),
            "current_branch": repo.active_branch.name,
            "latest_commit": {
                "sha": repo.head.commit.hexsha[:8],
                "message": repo.head.commit.message.strip(),
                "author": str(repo.head.commit.author),
                "date": repo.head.commit.committed_datetime.isoformat()
            }
        }
    
    def _should_ignore(self, path: Path) -> bool:
        """Check if file should be ignored in analysis."""
        ignore_dirs = {
            '.git', 'node_modules', '__pycache__', '.pytest_cache',
            'venv', '.venv', 'build', 'dist', '.next'
        }
        
        for part in path.parts:
            if part in ignore_dirs:
                return True
        
        return False
    
    def cleanup(self, project_id: str) -> bool:
        """
        Remove repository from workspace.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Success boolean
        """
        if project_id in self.repos:
            try:
                repo = self.repos[project_id]
                repo.close()
                repo.git.clear_cache()
            except Exception:
                pass
            del self.repos[project_id]
        
        repo_path = self.workspace_dir / project_id
        if repo_path.exists():
            try:
                import shutil
                shutil.rmtree(repo_path, ignore_errors=True)
                logger.info(f"Cleaned up repository: {project_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to cleanup {project_id}: {e}")
                return False
        
        return True
    
    def create_safety_tag(
        self,
        project_id: str,
        tag_name: str
    ) -> Tuple[bool, str]:
        """
        Create a lightweight tag as a restore point before risky operations.
        
        Args:
            project_id: Project identifier
            tag_name: Tag name (e.g., 'acea-pre-rollback-20260212')
            
        Returns:
            (success, message)
        """
        repo = self.repos.get(project_id)
        if not repo:
            return (False, f"No repo found for project {project_id}")
        
        try:
            # Create lightweight tag at current HEAD
            repo.create_tag(tag_name, message=f"ACEA safety tag: {tag_name}")
            logger.info(f"Created safety tag: {tag_name}")
            return (True, f"Safety tag created: {tag_name}")
            
        except GitCommandError as e:
            if "already exists" in str(e):
                logger.warning(f"Safety tag {tag_name} already exists, skipping")
                return (True, f"Tag {tag_name} already exists")
            logger.error(f"Failed to create safety tag: {e}")
            return (False, f"Tag creation failed: {str(e)}")
    
    def detect_conflicts(self, project_id: str) -> List[str]:
        """
        Check for merge conflicts in the current working tree.
        
        Returns:
            List of conflicting file paths (empty if no conflicts)
        """
        repo = self.repos.get(project_id)
        if not repo:
            return []
        
        try:
            # Check for unmerged entries
            conflicts = []
            for item in repo.index.unmerged_blobs():
                conflicts.append(str(item))
            
            if not conflicts:
                # Alternative: check for conflict markers in modified files
                for diff_item in repo.index.diff(None):
                    try:
                        file_path = Path(repo.working_dir) / diff_item.a_path
                        if file_path.exists():
                            content = file_path.read_text(encoding='utf-8', errors='replace')
                            if '<<<<<<< ' in content and '=======' in content and '>>>>>>> ' in content:
                                conflicts.append(diff_item.a_path)
                    except Exception:
                        pass
            
            return conflicts
            
        except Exception as e:
            logger.error(f"Conflict detection failed: {e}")
            return []
    
    async def safe_rollback(
        self,
        project_id: str,
        target_commit: str,
        test_runner=None
    ) -> Tuple[bool, str]:
        """
        Rollback with regression detection.
        
        Flow:
        1. Save current HEAD sha
        2. Create safety tag at current position
        3. git reset --hard target_commit
        4. If test_runner provided: run tests against rolled-back state
        5. If tests WORSE than before → revert rollback
        6. Return (success, message)
        
        Args:
            project_id: Project identifier
            target_commit: Commit SHA to roll back to
            test_runner: Optional async callable(project_dir) -> dict with 'passed' count
            
        Returns:
            (success, message)
        """
        repo = self.repos.get(project_id)
        if not repo:
            return (False, f"No repo found for project {project_id}")
        
        try:
            # Step 1: Save current position
            current_sha = repo.head.commit.hexsha
            logger.info(f"Safe rollback: current HEAD = {current_sha[:8]}, target = {target_commit[:8]}")
            
            # Step 2: Create safety tag
            from datetime import datetime
            tag_name = f"acea-pre-rollback-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            self.create_safety_tag(project_id, tag_name)
            
            # Step 3: Perform rollback
            repo.git.reset('--hard', target_commit)
            logger.info(f"Rolled back to {target_commit[:8]}")
            
            # Step 4: Regression detection (if test runner available)
            if test_runner:
                try:
                    repo_path = str(Path(repo.working_dir))
                    test_results = await test_runner(repo_path)
                    passed_after = test_results.get('passed', 0)
                    total_after = test_results.get('total', 0)
                    
                    # If tests are worse after rollback, revert it
                    if total_after > 0 and passed_after == 0:
                        logger.warning(
                            f"Safe rollback: ALL tests failed after rollback. "
                            f"Reverting to {current_sha[:8]}"
                        )
                        repo.git.reset('--hard', current_sha)
                        return (False, 
                            f"Rollback reverted — all tests failed after rolling back. "
                            f"Restored to {current_sha[:8]}")
                    
                    logger.info(
                        f"Safe rollback: Post-rollback tests: "
                        f"{passed_after}/{total_after} passed"
                    )
                    
                except Exception as test_err:
                    logger.warning(f"Safe rollback: Test runner failed: {test_err}")
                    # Don't revert on test runner failure — rollback itself succeeded
            
            return (True, 
                f"Rolled back to {target_commit[:8]} "
                f"(safety tag: {tag_name}, previous: {current_sha[:8]})")
            
        except GitCommandError as e:
            logger.error(f"Safe rollback failed: {e}")
            return (False, f"Rollback failed: {str(e)}")
    
    def get_commit_log(
        self,
        project_id: str,
        max_count: int = 20
    ) -> List[Dict[str, str]]:
        """
        Get recent commit history for a project.
        
        Returns:
            List of commit dicts with sha, message, author, date
        """
        repo = self.repos.get(project_id)
        if not repo:
            return []
        
        try:
            commits = []
            for commit in repo.iter_commits(max_count=max_count):
                commits.append({
                    "sha": commit.hexsha[:8],
                    "full_sha": commit.hexsha,
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat()
                })
            return commits
        except Exception as e:
            logger.error(f"Failed to get commit log: {e}")
            return []



# Singleton instance
_git_adapter = None

def get_git_adapter() -> GitAdapter:
    """Get singleton GitAdapter instance."""
    global _git_adapter
    if _git_adapter is None:
        _git_adapter = GitAdapter()
    return _git_adapter
