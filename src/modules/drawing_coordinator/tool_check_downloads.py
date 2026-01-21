"""
Scan Downloads folder for transmittal ZIP files.
Helps bridge the gap between manual browser downloads and processing.
"""

import zipfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional

from src.modules.drawing_coordinator.config import DEFAULT_DOWNLOADS_PATH, MAX_TRANSMITTAL_SIZE
from src.modules.drawing_coordinator.email.email_pattern_detector import EmailPatternDetector


def _validate_zip(file_path: Path) -> bool:
    """Check if the file is a valid ZIP archive."""
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            zf.namelist()
        return True
    except (zipfile.BadZipFile, Exception):
        return False


def _get_file_age_minutes(file_path: Path) -> float:
    """Get the age of a file in minutes based on modification time."""
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    age = datetime.now() - mtime
    return age.total_seconds() / 60


def scan_downloads_for_transmittals(
        job_number: str = None,
        minutes_ago: int = 15
) -> Dict:
    """
    Scans Downloads folder for recent transmittal ZIP files.

    Useful after manually downloading files from cloud storage links
    (SharePoint, WeTransfer, etc.) to find them for processing.

    Args:
        job_number: Optional filter - only return files matching this job number
        minutes_ago: Only look at files modified in last N minutes (default 15, max 120)

    Returns:
        {
            "success": True,
            "downloads_folder": "C:\\Users\\...\\Downloads",
            "time_window_minutes": 15,
            "files_found": [
                {
                    "path": "C:\\Users\\...\\Downloads\\6516_T077.zip",
                    "filename": "6516_T077.zip",
                    "size_mb": 45.2,
                    "modified": "2025-12-08T18:15:00",
                    "age_minutes": 5,
                    "detected_job": "6516",
                    "detected_transmittal": "T077",
                    "detected_type": "IFF",
                    "is_valid_zip": True,
                    "size_warning": False,
                    "ready_for_processing": True
                }
            ],
            "ready_count": 2,
            "total_found": 2
        }
    """
    # Clamp minutes_ago to valid range
    minutes_ago = max(1, min(120, minutes_ago))

    downloads_path = DEFAULT_DOWNLOADS_PATH

    if not downloads_path.exists():
        return {
            "success": False,
            "error": f"Downloads folder not found: {downloads_path}",
            "downloads_folder": str(downloads_path),
            "files_found": []
        }

    detector = EmailPatternDetector()
    cutoff_time = datetime.now() - timedelta(minutes=minutes_ago)

    files_found = []

    # Scan for ZIP files in Downloads folder
    for file_path in downloads_path.glob("*.zip"):
        try:
            stat = file_path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime)

            # Skip files older than cutoff
            if mtime < cutoff_time:
                continue

            filename = file_path.name
            size_bytes = stat.st_size
            size_mb = round(size_bytes / (1024 * 1024), 2)
            age_minutes = round(_get_file_age_minutes(file_path), 1)

            # Detect transmittal metadata from filename
            detected_job = detector._extract_job_number(filename)
            detected_trans = detector._extract_transmittal_number(filename)
            detected_type = detector._detect_type(filename)

            # Apply job_number filter if specified
            if job_number and detected_job != job_number:
                continue

            # Validate ZIP integrity
            is_valid_zip = _validate_zip(file_path)
            
            # Check for oversized files
            size_warning = size_bytes > MAX_TRANSMITTAL_SIZE

            # Ready if valid ZIP and not oversized
            ready_for_processing = is_valid_zip and not size_warning

            files_found.append({
                "path": str(file_path),
                "filename": filename,
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "modified": mtime.isoformat(),
                "age_minutes": age_minutes,
                "detected_job": detected_job,
                "detected_transmittal": detected_trans,
                "detected_type": detected_type,
                "is_valid_zip": is_valid_zip,
                "size_warning": size_warning,
                "ready_for_processing": ready_for_processing
            })

        except Exception:
            # Skip files we can't read
            continue

    # Sort by modification time (newest first)
    files_found.sort(key=lambda x: x["modified"], reverse=True)

    ready_count = sum(1 for f in files_found if f["ready_for_processing"])

    return {
        "success": True,
        "downloads_folder": str(downloads_path),
        "time_window_minutes": minutes_ago,
        "files_found": files_found,
        "total_found": len(files_found),
        "ready_count": ready_count
    }
