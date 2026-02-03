"""
Centralized logging utility for FabCore Agent.

Provides file-based logging to logs/ops.log in the agent's data directory,
with support for console output and structured log entries.
"""
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class AgentLogger:
    """
    Centralized logger for all agent operations.
    
    Logs to:
    - %LOCALAPPDATA%/FabCore/Agent/logs/ops.log (rotating, max 5MB x 3 files)
    - Console (stdout)
    
    Usage:
        from src.utils.logger import agent_logger
        
        agent_logger.info("Something happened")
        agent_logger.error("Something went wrong", exc_info=True)
    """
    
    _instance: Optional['AgentLogger'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if AgentLogger._initialized:
            return
        
        AgentLogger._initialized = True
        
        # Determine log directory
        if getattr(sys, "frozen", False):
            # Running as exe - use AppData
            self.log_dir = Path(os.environ.get("LOCALAPPDATA", ".")) / "FabCore" / "Agent" / "logs"
        else:
            # Running as script - use project root
            self.log_dir = Path(__file__).parent.parent.parent / "logs"
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "ops.log"
        
        # Create the logger
        self._logger = logging.getLogger("FabCoreAgent")
        self._logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers if called multiple times
        if not self._logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """Configure file and console handlers."""
        # File handler with rotation (5MB max, keep 3 backups)
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        
        self._logger.addHandler(file_handler)
        self._logger.addHandler(console_handler)

        # Capture websockets library warnings/errors
        ws_logger = logging.getLogger("websockets")
        ws_logger.setLevel(logging.WARNING)
        ws_logger.addHandler(file_handler)
    
    # =========================================================================
    # Standard logging methods
    # =========================================================================
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message."""
        self._logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message."""
        self._logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message."""
        self._logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message."""
        self._logger.error(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log error with exception traceback."""
        self._logger.exception(msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Log critical message."""
        self._logger.critical(msg, *args, **kwargs)
    
    # =========================================================================
    # Structured logging helpers
    # =========================================================================
    
    def operation(self, operation: str, status: str, details: str = ""):
        """
        Log a structured operation entry.
        
        Args:
            operation: Name of the operation (e.g., "update", "transmittal")
            status: Status (e.g., "started", "completed", "failed")
            details: Additional details
        """
        msg = f"[{operation.upper()}] {status}"
        if details:
            msg += f" - {details}"
        self._logger.info(msg)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a child logger for a specific module.
        
        Args:
            name: Module name (e.g., "updater", "filesystem")
            
        Returns:
            Logger instance that inherits handlers from the main logger
        """
        return self._logger.getChild(name)


# Singleton instance
agent_logger = AgentLogger()


def get_logger(name: str) -> logging.Logger:
    """
    Convenience function to get a module-specific logger.
    
    Usage:
        from src.utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Module loaded")
    """
    return agent_logger.get_logger(name)
