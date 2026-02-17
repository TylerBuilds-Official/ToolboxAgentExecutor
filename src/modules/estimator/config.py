"""Configuration constants for Estimator module"""
from pathlib import Path
import os


# =============================================================================
# Paths
# =============================================================================

# Default output path for classification breakout results
DEFAULT_OUTPUT_PATH = Path(os.path.expanduser("~")) / "Desktop" / "Fabcore" / "EstimatorTools" / "Classification"

# =============================================================================
# Pipeline Defaults
# =============================================================================

# Max workers for parallel classification
DEFAULT_MAX_WORKERS  = 12

# Default image rendering dimension
DEFAULT_MAX_IMAGE_DIM = 2048

# OCR zoom factor
DEFAULT_OCR_ZOOM = 4.0
