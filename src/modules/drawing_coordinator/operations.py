"""
Drawing Coordinator Module

Provides transmittal processing operations for the agent.
Requires 'drawing_coordinator' specialty permission.
"""
from typing import Optional
from src.modules.base import BaseModule
from src.modules.drawing_coordinator.tool_process_transmittal import process_transmittal
from src.modules.drawing_coordinator.tool_check_downloads import scan_downloads_for_transmittals
from src.modules.drawing_coordinator.config import DEFAULT_OUTPUT_PATH


class DrawingCoordinatorModule(BaseModule):
    """
    Drawing Coordinator operations module.
    
    Handles transmittal processing workflows for steel fabrication:
    - Scan downloads folder for transmittal ZIPs
    - ZIP extraction and classification
    - File organization by type (fab, erection, NC, etc.)
    - Distribution to network destinations
    """
    name = 'drawing_coordinator'

    # =========================================================================
    # Downloads Scanning
    # =========================================================================

    async def scan_downloads_for_transmittals(
        self,
        job_number: Optional[str] = None,
        minutes_ago: int = 15
    ) -> dict:
        """
        Scan Downloads folder for recent transmittal ZIP files.
        
        Use this to find transmittals after manual download from cloud links
        (SharePoint, WeTransfer, etc.), then call process_transmittal for each.
        
        Args:
            job_number: Optional filter - only return files matching this job
            minutes_ago: Look at files modified in last N minutes (default 15, max 120)
            
        Returns:
            Dict containing:
                - success: bool
                - downloads_folder: path scanned
                - files_found: list of detected transmittal ZIPs with metadata
                - ready_count: number ready for processing
        """
        try:
            result = scan_downloads_for_transmittals(
                job_number=job_number,
                minutes_ago=minutes_ago
            )
            
            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Scan failed"))
                
        except Exception as e:
            return self._error(f"Failed to scan downloads: {e}")

    # =========================================================================
    # Transmittal Processing
    # =========================================================================

    async def process_transmittal(
        self,
        zip_path: str,
        output_path: Optional[str] = None,
        job_number: Optional[str] = None,
        distribute_data: bool = True
    ) -> dict:
        """
        Process a transmittal ZIP file through the full pipeline.
        
        Args:
            zip_path: Full path to the input ZIP file
            output_path: Directory for output (default: ~/Desktop/Fabcore/DrawingCoordinatorTools/Output)
            job_number: Optional 4-digit job number. Auto-detected if not provided.
            distribute_data: Whether to distribute files to network destinations (default: True)
            
        Returns:
            Dict containing:
                - success: bool
                - job_data: dict with job info, file counts, distribution results
                - logs: summarized log entries
                - status: final status message
                - error: error message if failed
                - log_file: path to detailed log file
        """
        try:
            result = process_transmittal(
                zip_path=zip_path,
                output_path=output_path,
                job_number=job_number,
                distribute_data=distribute_data
            )
            
            if result.get("success"):
                return self._success(**result)
            else:
                return self._error(result.get("error", "Unknown error"))
                
        except FileNotFoundError as e:
            return self._error(f"ZIP file not found: {e}")
        except ValueError as e:
            return self._error(f"Invalid input: {e}")
        except Exception as e:
            return self._error(f"Processing failed: {e}")

    async def get_default_output_path(self) -> dict:
        """
        Get the default output path for transmittal processing.
        
        Returns:
            Dict with the default output path
        """
        return self._success(
            path=str(DEFAULT_OUTPUT_PATH),
            exists=DEFAULT_OUTPUT_PATH.exists()
        )
