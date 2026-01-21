"""
Configuration constants for Document Creation module.
"""
from pathlib import Path
import os

# =============================================================================
# Paths
# =============================================================================

# Default output path for generated documents
DEFAULT_OUTPUT_PATH = Path(os.path.expanduser("~")) / "Desktop" / "Fabcore" / "Reports"

# Module root (for accessing skills and templates)
MODULE_ROOT = Path(__file__).parent

# Skills directory - AI reads these for guidance
SKILLS_PATH = MODULE_ROOT / "skills"

# Templates directory - base files for document generation
TEMPLATES_PATH = MODULE_ROOT / "templates"

# =============================================================================
# Defaults
# =============================================================================

# Default HTML report settings
DEFAULT_REPORT_TITLE = "FabCore Report"
DEFAULT_REPORT_THEME = "light"  # light or dark
