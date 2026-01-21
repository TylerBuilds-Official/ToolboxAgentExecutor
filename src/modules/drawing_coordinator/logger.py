"""
Headless Logger for Drawing Coordinator operations.

Provides logging without UI dependencies - stores entries in memory
for later retrieval and optional file export.
"""
from datetime import datetime
from typing import Optional


class HeadlessLogger:
    """
    Simple in-memory logger for headless/agent operation.
    
    Mimics the interface expected by transmittal processing components:
    - append_log_action(message, level)
    - set_status_bar(message)
    - as_dict() -> {"entries": [...], "status": str}
    """
    
    def __init__(self):
        self._entries: list[dict] = []
        self._status: str = "Idle"
    
    def append_log_action(self, message: str, level: str = "Info") -> None:
        """
        Add a log entry.
        
        Args:
            message: Log message
            level: One of "Info", "Success", "Warning", "Error"
        """
        self._entries.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message
        })
    
    def set_status_bar(self, message: str) -> None:
        """Update the current status."""
        self._status = message
    
    @property
    def status(self) -> str:
        """Get current status."""
        return self._status
    
    def as_dict(self) -> dict:
        """Export all logs as a dictionary."""
        return {
            "entries": self._entries,
            "status": self._status
        }
    
    def clear(self) -> None:
        """Clear all log entries."""
        self._entries = []
        self._status = "Idle"
    
    def get_errors(self) -> list[dict]:
        """Get only error entries."""
        return [e for e in self._entries if e["level"] == "Error"]
    
    def get_warnings(self) -> list[dict]:
        """Get only warning entries."""
        return [e for e in self._entries if e["level"] == "Warning"]
