"""
Standalone update applier script.

This script is bundled with each release and runs AFTER the main agent exits.
It waits for the agent to exit, copies new files over, and restarts the agent.

Usage:
    python apply_updates.py --target <install_dir> --source <extracted_update_dir> 
                            --restart-exe <exe_path> --rollback-dir <rollback_dir>
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Configure logging
LOG_FILE = Path(os.environ.get("LOCALAPPDATA", ".")) / "FabCore" / "Agent" / "update.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def wait_for_process_exit(exe_path: str, timeout: int = 30) -> bool:
    """
    Wait for the main application to exit.
    
    Args:
        exe_path: Path to the executable to wait for
        timeout: Maximum seconds to wait
        
    Returns:
        True if process exited, False if timeout
    """
    try:
        import psutil
        has_psutil = True
    except ImportError:
        has_psutil = False
        logger.warning("psutil not available, using simple delay instead")
    
    exe_name = Path(exe_path).name.lower()
    start_time = time.time()
    
    logger.info(f"Waiting for {exe_name} to exit (timeout: {timeout}s)...")
    
    if has_psutil:
        while time.time() - start_time < timeout:
            running = False
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    proc_name = proc.info.get('name', '').lower()
                    proc_exe = proc.info.get('exe', '') or ''
                    
                    if proc_name == exe_name or exe_name in proc_exe.lower():
                        running = True
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if not running:
                logger.info(f"{exe_name} has exited")
                return True
            
            time.sleep(0.5)
        
        logger.warning(f"Timeout waiting for {exe_name} to exit")
        return False
    else:
        # Fallback: just wait a fixed time
        time.sleep(5)
        return True


def copy_update_files(source: Path, target: Path) -> bool:
    """
    Copy files from extracted update to target directory.
    
    Args:
        source: Directory containing extracted update files
        target: Target installation directory
        
    Returns:
        True if successful
    """
    logger.info(f"Copying files from {source} to {target}...")
    
    # Files/dirs to skip
    skip_items = {
        'apply_updates.py',  # Don't copy ourselves
        '__pycache__',
        '.git',
        '.venv',
        'venv',
        'update.log',
        'config.yml',  # Preserve user config - TODO: merge configs instead?
    }
    
    copied_count = 0
    error_count = 0
    
    for item in source.iterdir():
        if item.name in skip_items or item.name.startswith('.'):
            logger.debug(f"Skipping: {item.name}")
            continue
        
        dest = target / item.name
        
        try:
            # Remove existing item first
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            
            # Copy new item
            if item.is_dir():
                shutil.copytree(item, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copy2(item, dest)
            
            logger.info(f"  Copied: {item.name}")
            copied_count += 1
            
        except Exception as e:
            logger.error(f"  Failed to copy {item.name}: {e}")
            error_count += 1
    
    logger.info(f"Copied {copied_count} items, {error_count} errors")
    return error_count == 0


def restart_application(exe_path: str, working_dir: str) -> bool:
    """
    Restart the application.
    
    Args:
        exe_path: Path to the executable to start
        working_dir: Working directory to start in
        
    Returns:
        True if started successfully
    """
    logger.info(f"Restarting application: {exe_path}")
    
    try:
        subprocess.Popen(
            [exe_path],
            cwd=working_dir,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("Application restarted successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to restart application: {e}")
        return False


def rollback(rollback_dir: Path, target: Path) -> bool:
    """
    Restore the previous version from rollback backup.
    
    Args:
        rollback_dir: Directory containing the backup
        target: Target installation directory
        
    Returns:
        True if successful
    """
    if not rollback_dir.exists():
        logger.error(f"Rollback directory not found: {rollback_dir}")
        return False
    
    logger.info(f"Rolling back from {rollback_dir}...")
    
    try:
        for item in rollback_dir.iterdir():
            if item.name in ('rollback_version.txt', '__pycache__'):
                continue
            
            dest = target / item.name
            
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            
            logger.info(f"  Restored: {item.name}")
        
        logger.info("Rollback complete")
        return True
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return False


def cleanup(source_dir: Path, keep_zip: bool = True):
    """
    Clean up temporary files after update.
    
    Args:
        source_dir: Extracted update directory to remove
        keep_zip: Whether to keep the downloaded zip file
    """
    logger.info("Cleaning up temporary files...")
    
    try:
        if source_dir.exists():
            shutil.rmtree(source_dir)
            logger.info(f"  Removed: {source_dir}")
    except Exception as e:
        logger.warning(f"  Failed to remove {source_dir}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Apply FabCore Agent update")
    parser.add_argument("--target", required=True, help="Target installation directory")
    parser.add_argument("--source", required=True, help="Source directory with extracted update files")
    parser.add_argument("--restart-exe", required=True, help="Executable to restart after update")
    parser.add_argument("--rollback-dir", required=True, help="Directory containing rollback backup")
    parser.add_argument("--no-restart", action="store_true", help="Don't restart after update")
    args = parser.parse_args()
    
    target = Path(args.target).resolve()
    source = Path(args.source).resolve()
    rollback_dir = Path(args.rollback_dir).resolve()
    restart_exe = args.restart_exe
    
    logger.info("=" * 60)
    logger.info("FabCore Agent Update")
    logger.info("=" * 60)
    logger.info(f"Target:      {target}")
    logger.info(f"Source:      {source}")
    logger.info(f"Rollback:    {rollback_dir}")
    logger.info(f"Restart exe: {restart_exe}")
    logger.info("=" * 60)
    
    # Step 1: Wait for the main app to exit
    if not wait_for_process_exit(restart_exe, timeout=30):
        logger.warning("Application may still be running, proceeding anyway...")
    
    # Extra safety delay
    time.sleep(1)
    
    # Step 2: Copy update files
    success = copy_update_files(source, target)
    
    if not success:
        logger.error("Update failed, attempting rollback...")
        if rollback(rollback_dir, target):
            logger.info("Rollback successful, restarting previous version")
        else:
            logger.error("Rollback also failed! Manual intervention required.")
            logger.error(f"Backup may be available at: {rollback_dir}")
            sys.exit(1)
    
    # Step 3: Cleanup
    cleanup(source)
    
    # Step 4: Restart
    if not args.no_restart:
        time.sleep(1)  # Brief pause before restart
        if not restart_application(restart_exe, str(target)):
            logger.error("Failed to restart application")
            sys.exit(1)
    
    logger.info("Update complete!")
    sys.exit(0)


if __name__ == "__main__":
    main()
