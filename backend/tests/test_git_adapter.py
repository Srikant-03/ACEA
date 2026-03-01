# backend/tests/test_git_adapter.py
import pytest
import os
import shutil
import time
from pathlib import Path
from app.core.git_adapter import GitAdapter
from git import Repo

# Use a temporary directory for tests
TEST_REPO_DIR = Path("tmp_test_repos")

def _force_remove_readonly(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree`` on Windows.
    Handles read-only files and file-in-use errors from Git.
    """
    import stat
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    try:
        func(path)
    except PermissionError:
        # File still in use by Git process — skip, will retry
        pass

@pytest.fixture(autouse=True)
def setup_teardown():
    import gc
    
    # Setup - force GC to release any leftover Git handles
    gc.collect()
    
    if TEST_REPO_DIR.exists():
        shutil.rmtree(TEST_REPO_DIR, ignore_errors=True)
    TEST_REPO_DIR.mkdir(exist_ok=True)
    
    yield
    
    # Teardown - force GC to close GitPython handles
    gc.collect()
    
    if TEST_REPO_DIR.exists():
        for i in range(5):
            try:
                shutil.rmtree(TEST_REPO_DIR, ignore_errors=True)
                if not TEST_REPO_DIR.exists():
                    break
            except Exception:
                pass
            time.sleep(0.5)

@pytest.mark.asyncio
async def test_clone_repository():
    adapter = GitAdapter(workspace_dir=str(TEST_REPO_DIR))
    
    # Use a small public repo
    repo_url = "https://github.com/octocat/Hello-World.git"
    project_id = "test_project_clone"
    
    success, msg, path = adapter.clone_repository(
        project_id,
        repo_url
    )
    
    assert success
    assert path is not None
    assert (TEST_REPO_DIR / project_id).exists()
    assert (TEST_REPO_DIR / project_id / ".git").exists()
    
    # Cleanup explicitly
    adapter.cleanup(project_id) # Should close handles
    adapter.repos.clear()

@pytest.mark.asyncio
async def test_create_branch():
    adapter = GitAdapter(workspace_dir=str(TEST_REPO_DIR))
    repo_url = "https://github.com/octocat/Hello-World.git"
    project_id = "test_project_branch"
    
    # Clone first
    adapter.clone_repository(project_id, repo_url)
    
    # Create branch
    branch_name = "test-feature-branch"
    success, msg = adapter.create_feature_branch(project_id, branch_name)
    
    assert success
    assert f"Branch '{branch_name}' created" in msg
    
    # Verify
    repo = adapter.repos[project_id]
    assert repo.active_branch.name == branch_name
    
    adapter.cleanup(project_id)

@pytest.mark.asyncio
async def test_commit_changes():
    adapter = GitAdapter(workspace_dir=str(TEST_REPO_DIR))
    repo_url = "https://github.com/octocat/Hello-World.git"
    project_id = "test_project_commit"
    
    adapter.clone_repository(project_id, repo_url)
    repo_path = Path(adapter.repos[project_id].working_dir)
    
    # Configure git user for commit
    repo = adapter.repos[project_id]
    with repo.config_writer() as git_config:
        git_config.set_value('user', 'email', 'test@example.com')
        git_config.set_value('user', 'name', 'Test User')
    
    # Create a new file
    new_file = repo_path / "new_file.txt"
    new_file.write_text("Hello Git!")
    
    # Commit
    success, msg, sha = adapter.commit_changes(project_id, "Add new file")
    
    if not success:
         print(f"Commit failed: {msg}")
    
    assert success
    assert sha is not None
    
    # Verify log
    assert repo.head.commit.message.strip() == "Add new file"
    
    adapter.cleanup(project_id)

