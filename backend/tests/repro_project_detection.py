import sys
import os
import shutil
from pathlib import Path
import unittest

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.project_runner import ProjectRunner

class TestProjectDetection(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("temp_repro_test")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_rails_missing_gemfile(self):
        """Test Rails project with bin/rails but no Gemfile (flat structure)"""
        # Create structure: app/, bin/rails, config/routes.rb
        (self.test_dir / "app").mkdir()
        (self.test_dir / "bin").mkdir()
        (self.test_dir / "config").mkdir()
        (self.test_dir / "bin" / "rails").touch()
        (self.test_dir / "config" / "routes.rb").touch()

        runner = ProjectRunner(str(self.test_dir), "test_rails")
        self.assertEqual(runner.frontend_path, self.test_dir, 
                         "Should detect root as frontend path for Rails app without Gemfile")

    def test_django_manage_py(self):
        """Test Django project with manage.py (flat structure)"""
        (self.test_dir / "manage.py").touch()
        
        runner = ProjectRunner(str(self.test_dir), "test_django")
        self.assertEqual(runner.frontend_path, self.test_dir,
                         "Should detect root as frontend path for Django app")

    def test_go_project(self):
        """Test Go project with go.mod or main.go"""
        (self.test_dir / "main.go").touch()
        
        runner = ProjectRunner(str(self.test_dir), "test_go")
        self.assertEqual(runner.frontend_path, self.test_dir,
                         "Should detect root for Go app")

    def test_nested_frontend(self):
        """Test standard nested structure still works"""
        frontend = self.test_dir / "frontend"
        frontend.mkdir()
        (frontend / "package.json").touch()
        
        runner = ProjectRunner(str(self.test_dir), "test_nested")
        self.assertEqual(runner.frontend_path, frontend,
                         "Should detect nested frontend directory")

    def test_empty_directory_fallback(self):
        """Test empty directory falls back to root if frontend/ is missing"""
        # No files, no frontend dir
        runner = ProjectRunner(str(self.test_dir), "test_empty")
        self.assertEqual(runner.frontend_path, self.test_dir,
                         "Should fallback to root if frontend/ is missing")
        
    def test_empty_directory_with_frontend_folder(self):
        """Test legacy behavior: if frontend/ exists but is empty, prefer it (for now)"""
        (self.test_dir / "frontend").mkdir()
        runner = ProjectRunner(str(self.test_dir), "test_empty_nested")
        self.assertEqual(runner.frontend_path, self.test_dir / "frontend",
                         "Should prefer existing frontend/ directory even if empty (legacy behavior)")

if __name__ == "__main__":
    unittest.main()
