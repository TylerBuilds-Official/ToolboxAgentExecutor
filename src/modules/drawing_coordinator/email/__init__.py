"""
Email processing utilities for Drawing Coordinator.

Provides pattern detection for extracting transmittal metadata
from email subjects, bodies, and attachment names.
"""

from .email_pattern_detector import EmailPatternDetector

__all__ = ["EmailPatternDetector"]
