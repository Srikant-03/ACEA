# ACEA Sentinel - Cleanup Scheduler
# Removes old projects to prevent disk usage buildup

import os
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from app.core.config import settings
from app.core.filesystem import BASE_PROJECTS_DIR

logger = logging.getLogger(__name__)


def cleanup_old_projects():
    """Delete projects older than retention period."""
    
    if not settings.ENABLE_AUTO_CLEANUP:
        return 0
    
    retention = timedelta(hours=settings.PROJECT_RETENTION_HOURS)
    cutoff = datetime.now() - retention
    count = 0
    
    if not BASE_PROJECTS_DIR.exists():
        return 0
    
    for project_dir in BASE_PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        
        try:
            # Check modification time
            mtime = datetime.fromtimestamp(project_dir.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(project_dir)
                count += 1
                logger.info(f"Cleaned up old project: {project_dir.name}")
        except Exception as e:
            logger.error(f"Failed to clean up {project_dir.name}: {e}")
    
    if count > 0:
        logger.info(f"Cleaned up {count} old projects")
    
    return count


def get_disk_usage() -> dict:
    """Get disk usage statistics for projects directory."""
    
    total_size = 0
    project_count = 0
    
    if BASE_PROJECTS_DIR.exists():
        for project_dir in BASE_PROJECTS_DIR.iterdir():
            if project_dir.is_dir():
                project_count += 1
                for file in project_dir.rglob("*"):
                    if file.is_file():
                        total_size += file.stat().st_size
    
    return {
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "project_count": project_count,
        "max_size_mb": settings.MAX_PROJECT_SIZE_MB
    }


def start_cleanup_scheduler():
    """Start background cleanup scheduler (APScheduler)."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(cleanup_old_projects, 'interval', hours=1)
        scheduler.start()
        logger.info("Cleanup scheduler started (runs every hour)")
        return scheduler
    except ImportError:
        logger.warning("APScheduler not installed. Auto-cleanup disabled.")
        logger.warning("Install with: pip install apscheduler")
        return None
