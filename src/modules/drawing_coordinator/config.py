"""
Configuration constants for Drawing Coordinator module.
"""
from pathlib import Path
import os

# =============================================================================
# Paths
# =============================================================================

# Default output path for transmittal processing
DEFAULT_OUTPUT_PATH = Path(os.path.expanduser("~")) / "Desktop" / "Fabcore" / "DrawingCoordinatorTools" / "Output"

# Default downloads folder for transmittal scanning
DEFAULT_DOWNLOADS_PATH = Path(os.path.expanduser("~")) / "Downloads"

# =============================================================================
# Feature Flags
# =============================================================================

# Distribution: Copy processed files to network destinations (SD drive, NC drive)
# Set to False to disable distribution while keeping the handler code intact
DISTRIBUTION_ENABLED = False

# =============================================================================
# Size Limits
# =============================================================================

# Maximum transmittal ZIP size (1.5 GB) - files larger than this are flagged
MAX_TRANSMITTAL_SIZE = 1024 * 1024 * 1024 * 1.5  # 1.5 GB in bytes

# Email attachment size limits (for future email scanning)
MIN_ATTACHMENT_SIZE = 1024 * 10           # 10 KB - tiny files unlikely to be transmittals  
MAX_ATTACHMENT_SIZE = 1024 * 1024 * 500   # 500 MB - email attachment practical limit
