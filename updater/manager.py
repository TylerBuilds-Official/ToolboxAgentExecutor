import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional, Callable

import aiohttp

from updater._dataclass import UpdateInfo

# Use centralized logger
try:
    from src.utils.logger import get_logger
    logger = get_logger("updater")
except ImportError:
    # Fallback if running standalone
    import logging
    logger = logging.getLogger(__name__)


class UpdateManager:
    """
    Handles downloading, applying, and rolling back agent updates.
    
    Updates can be triggered via WebSocket notification from the server.
    - force=False: Download in background, notify when ready, user/tray triggers apply
    - force=True: Download and apply immediately, restart automatically
    """
    
    def __init__(
        self,
        current_version: str,
        server_base_url: str,
        on_update_ready: Optional[Callable[[UpdateInfo], None]] = None,
        on_force_update: Optional[Callable[[UpdateInfo], None]] = None
    ):
        self._current_version = current_version
        self._server_base_url = server_base_url.rstrip("/")
        self._on_update_ready = on_update_ready
        self._on_force_update = on_force_update

        # Paths
        # When frozen (exe), app_dir is the exe's directory
        # When running as script, app_dir is the project root
        if getattr(sys, "frozen", False):
            self.app_dir = Path(sys.executable).parent.resolve()
        else:
            # Go up from updater/ to project root
            self.app_dir = Path(__file__).parent.parent.resolve()
        
        self.data_dir = Path(os.environ.get("LOCALAPPDATA", ".")) / "FabCore" / "Agent"
        self.updates_dir = self.data_dir / "updates"
        self.rollback_dir = self.data_dir / "rollback"

        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.updates_dir.mkdir(exist_ok=True)

        self._pending_update: Optional[UpdateInfo] = None
        self._download_task: Optional[asyncio.Task] = None

    @property
    def current_version(self) -> str:
        return self._current_version

    @property
    def has_pending_update(self) -> bool:
        return self._pending_update is not None

    @property
    def pending_version(self) -> Optional[str]:
        return self._pending_update.version if self._pending_update else None

    @property
    def pending_update(self) -> Optional[UpdateInfo]:
        return self._pending_update

    # =========================================================================
    # Public API
    # =========================================================================

    async def handle_update_notification(self, data: dict) -> dict:
        """
        Handle update_available or update_required message from server.
        
        Args:
            data: Message payload with version, force, changelog, etc.
            
        Returns:
            Acknowledgment response to send back to server
        """
        # Ensure download_url is a full URL
        download_url = data.get("download_url", "")
        if download_url and not download_url.startswith("http"):
            # Relative URL - prepend base URL
            download_url = f"{self._server_base_url}{download_url}"
        elif not download_url:
            download_url = f"{self._server_base_url}/agent/download/{data.get('version')}"
        
        # Build UpdateInfo from notification data
        update = UpdateInfo(
            version=data.get("version"),
            force=data.get("force", False),
            changelog=data.get("changelog", ""),
            download_url=download_url,
            checksum=data.get("checksum"),
            min_version=data.get("min_version")
        )

        # Check if we actually need this update
        if not self._needs_update(update.version):
            logger.info(f"Already at version {self._current_version}, ignoring update to {update.version}")
            return {"type": "update_ack", "version": update.version, "status": "already_current"}

        # Check minimum version requirement - force update if we're too far behind
        if update.min_version and self._version_less_than(self._current_version, update.min_version):
            logger.warning(f"Current version {self._current_version} is below minimum {update.min_version}. Forcing update.")
            update.force = True

        logger.info(f"Update available: {self._current_version} → {update.version} (force={update.force})")

        if update.force:
            # Force update - notify callback, then download and apply immediately
            if self._on_force_update:
                self._on_force_update(update)
            await self._download_and_apply(update)
            # Note: If successful, we won't reach here (sys.exit called)
            return {"type": "update_ack", "version": update.version, "status": "applying"}
        else:
            # Optional update - download in background, notify when ready
            self._pending_update = update
            self._download_task = asyncio.create_task(self._download_update(update))
            self._download_task.add_done_callback(self._on_download_complete)
            return {"type": "update_ack", "version": update.version, "status": "downloading"}

    async def apply_pending_update(self) -> bool:
        """
        Apply the pending update (called by user action, e.g., tray menu click).
        
        Returns:
            False if no pending update or file missing. Does not return on success (exits).
        """
        if not self._pending_update:
            logger.warning("No pending update to apply")
            return False
        
        return await self._apply_update(self._pending_update.version)

    async def check_for_update(self) -> Optional[UpdateInfo]:
        """
        Manually check for updates by polling the server.
        Use this for startup check or manual "Check for Updates" button.
        
        Returns:
            UpdateInfo if update available, None otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self._server_base_url}/agent/version"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    if self._needs_update(data.get("version", "")):
                        # Ensure download_url is a full URL
                        download_url = data.get("download_url", "")
                        if download_url and not download_url.startswith("http"):
                            download_url = f"{self._server_base_url}{download_url}"
                        elif not download_url:
                            download_url = f"{self._server_base_url}/agent/download/{data['version']}"
                        
                        return UpdateInfo(
                            version=data["version"],
                            force=data.get("force", False),
                            changelog=data.get("changelog", ""),
                            download_url=download_url,
                            checksum=data.get("checksum"),
                            min_version=data.get("min_version")
                        )
                    return None
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
            return None

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _on_download_complete(self, task: asyncio.Task):
        """Callback when background download completes."""
        try:
            task.result()  # Raise any exception that occurred
            logger.info(f"Update {self._pending_update.version} downloaded and ready")
            if self._on_update_ready and self._pending_update:
                self._on_update_ready(self._pending_update)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self._pending_update = None

    async def _download_update(self, update: UpdateInfo) -> Path:
        """Download update zip to local storage."""
        zip_path = self.updates_dir / f"FabCoreAgent_{update.version}.zip"

        if zip_path.exists():
            logger.info(f"Update {update.version} already downloaded: {zip_path}")
            return zip_path

        logger.info(f"Downloading update {update.version} from {update.download_url}...")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(update.download_url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    with open(zip_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size:
                                progress = (downloaded / total_size) * 100
                                logger.debug(f"Download progress: {progress:.1f}%")

            logger.info(f"Update {update.version} downloaded: {zip_path}")
            
            # TODO: Verify checksum if provided
            # if update.checksum:
            #     actual_checksum = self._compute_checksum(zip_path)
            #     if actual_checksum != update.checksum:
            #         zip_path.unlink()
            #         raise ValueError(f"Checksum mismatch: expected {update.checksum}, got {actual_checksum}")

            return zip_path
            
        except Exception as e:
            # Clean up partial download
            if zip_path.exists():
                zip_path.unlink()
            raise

    async def _download_and_apply(self, update: UpdateInfo):
        """Download and immediately apply an update (for forced updates)."""
        try:
            await self._download_update(update)
            await self._apply_update(update.version)
        except Exception as e:
            logger.error(f"Force update failed: {e}")
            raise

    async def _apply_update(self, version: str) -> bool:
        """
        Apply a downloaded update.
        
        This method:
        1. Creates a rollback backup of the current version
        2. Extracts the update zip
        3. Creates a batch script to copy files and restart
        4. Exits so the batch script can replace files
        
        Returns:
            False if setup fails. Does not return on success (exits).
        """
        zip_path = self.updates_dir / f"FabCoreAgent_{version}.zip"
        
        if not zip_path.exists():
            logger.error(f"Update file not found: {zip_path}")
            return False

        # Create rollback backup first
        await self._create_rollback_backup()

        # Extract to temp location
        extract_dir = self.updates_dir / f"extracted_{version}"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)

        logger.info(f"Extracting update to {extract_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)

        logger.info("Creating update batch script...")
        
        # Create a batch file that will:
        # 1. Wait for this process to exit
        # 2. Copy new files
        # 3. Restart the exe
        batch_path = self.updates_dir / "apply_update.bat"

        extract_str = str(extract_dir)
        app_str = str(self.app_dir)

        log_path = str(self.updates_dir / "update_batch.log")
        exe_path = f"{app_str}\\FabCoreAgent.exe"

        # Create the actual batch script
        batch_path = self.updates_dir / "apply_update.bat"
        batch_content = f"""@echo off
        setlocal

        echo FabCore Agent Updater > "{log_path}"
        echo Timestamp: %date% %time% >> "{log_path}"

        echo Waiting for agent to exit... >> "{log_path}"
        :WAIT_LOOP
        tasklist /FI "IMAGENAME eq FabCoreAgent.exe" 2>nul | find /I "FabCoreAgent.exe" >nul
        if %ERRORLEVEL%==0 (
            timeout /t 1 /nobreak >nul 2>&1
            goto WAIT_LOOP
        )
        echo Agent process exited >> "{log_path}"

        echo Waiting for file locks to release... >> "{log_path}"
        timeout /t 3 /nobreak >nul 2>&1

        echo Copying new files... >> "{log_path}"
        robocopy "{extract_str}" "{app_str}" /E /NFL /NDL /NJH /NJS /NC /NS /NP /W:3 /R:5 >> "{log_path}" 2>&1

        echo Verifying exe exists... >> "{log_path}"
        if not exist "{exe_path}" (
            echo ERROR: Exe not found after copy! >> "{log_path}"
            exit /b 1
        )

        echo Cleaning up extracted files... >> "{log_path}"
        rmdir /S /Q "{extract_str}" >nul 2>&1

        echo Launching updated agent... >> "{log_path}"
        timeout /t 2 /nobreak >nul 2>&1
        start "" "{exe_path}"

        echo Update complete! >> "{log_path}"
        endlocal
        """
        
        with open(batch_path, 'w') as f:
            f.write(batch_content)
        
        # Create VBScript launcher to run batch completely hidden
        vbs_path = self.updates_dir / "apply_update.vbs"
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c ""{batch_path}""", 0, True
Set fso = CreateObject("Scripting.FileSystemObject")
fso.DeleteFile "{vbs_path}", True
fso.DeleteFile "{batch_path}", True
'''
        
        with open(vbs_path, 'w') as f:
            f.write(vbs_content)
        
        logger.info(f"Launching updater script: {vbs_path}")
        
        # Launch the VBScript (wscript runs without console)
        subprocess.Popen(
            ['wscript.exe', str(vbs_path)],
            cwd=str(self.updates_dir),
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Exit so the batch script can replace our files
        logger.info("Exiting for update...")
        sys.exit(0)

    async def _create_rollback_backup(self):
        """Create a backup of the current version for potential rollback."""
        if self.rollback_dir.exists():
            shutil.rmtree(self.rollback_dir)

        self.rollback_dir.mkdir(parents=True)

        logger.info(f"Creating rollback backup at {self.rollback_dir}...")

        for item in self.app_dir.iterdir():
            # Skip hidden files, cache, and the updates directory itself
            if item.name.startswith('.') or item.name in ('__pycache__', '.venv', 'venv', '.git'):
                continue

            dest = self.rollback_dir / item.name
            try:
                if item.is_dir():
                    shutil.copytree(item, dest, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                else:
                    shutil.copy2(item, dest)
            except Exception as e:
                logger.warning(f"Failed to backup {item.name}: {e}")

        # Save version info for rollback identification
        version_file = self.rollback_dir / "rollback_version.txt"
        with open(version_file, "w") as f:
            f.write(self._current_version)

        logger.info(f"Rollback backup created: {self._current_version}")

    # =========================================================================
    # Version Comparison Helpers
    # =========================================================================

    def _needs_update(self, new_version: str) -> bool:
        """Check if new_version is newer than current version."""
        return self._version_greater_than(new_version, self._current_version)

    @staticmethod
    def _parse_version(v: str) -> tuple:
        """
        Parse version string into comparable tuple.
        
        Handles formats like:
        - "1.2.3" -> (1, 2, 3, '', 0)
        - "1.2.3a" -> (1, 2, 3, 'a', 0)
        - "1.2.3b" -> (1, 2, 3, 'b', 0)
        - "1.2.3-alpha" -> (1, 2, 3, 'alpha', 0)
        - "1.2.3-beta.2" -> (1, 2, 3, 'beta', 2)
        
        Returns tuple for comparison: (major, minor, patch, prerelease_type, prerelease_num)
        """
        if not v:
            return (0, 0, 0, '', 0)
        
        # Match: major.minor.patch followed by optional prerelease
        # Examples: 0.0.1, 0.0.1a, 0.0.1-alpha, 0.0.1-beta.2
        pattern = r'^(\d+)\.(\d+)\.(\d+)(?:[-.]?([a-zA-Z]+)(?:\.(\d+))?)?$'
        match = re.match(pattern, v)
        
        if not match:
            return (0, 0, 0, '', 0)
        
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3))
        prerelease_type = (match.group(4) or '').lower()  # 'a', 'b', 'alpha', 'beta', ''
        prerelease_num = int(match.group(5)) if match.group(5) else 0
        
        return (major, minor, patch, prerelease_type, prerelease_num)

    @staticmethod
    def _compare_versions(a: str, b: str) -> int:
        """
        Compare two version strings.
        
        Returns:
            -1 if a < b
             0 if a == b
             1 if a > b
        """
        pa = UpdateManager._parse_version(a)
        pb = UpdateManager._parse_version(b)
        
        # Compare major.minor.patch first
        for i in range(3):
            if pa[i] > pb[i]:
                return 1
            if pa[i] < pb[i]:
                return -1
        
        # Same major.minor.patch - compare prerelease
        # No prerelease (stable) > any prerelease
        # So "1.0.0" > "1.0.0a" > "1.0.0-alpha"
        pre_a = pa[3]
        pre_b = pb[3]
        
        if not pre_a and not pre_b:
            return 0  # Both stable
        if not pre_a:
            return 1  # a is stable, b has prerelease -> a > b
        if not pre_b:
            return -1  # a has prerelease, b is stable -> a < b
        
        # Both have prerelease - compare alphabetically
        # 'b' > 'a', 'beta' > 'alpha'
        if pre_a > pre_b:
            return 1
        if pre_a < pre_b:
            return -1
        
        # Same prerelease type - compare prerelease number
        if pa[4] > pb[4]:
            return 1
        if pa[4] < pb[4]:
            return -1
        
        return 0

    @staticmethod
    def _version_greater_than(a: str, b: str) -> bool:
        """Return True if version a > b."""
        return UpdateManager._compare_versions(a, b) > 0

    @staticmethod
    def _version_less_than(a: str, b: str) -> bool:
        """Return True if version a < b."""
        return UpdateManager._compare_versions(a, b) < 0
