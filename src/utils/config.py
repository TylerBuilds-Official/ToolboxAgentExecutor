import yaml
from pathlib import Path
from typing import Optional


class Config:
    """
    Configuration loader for the FabCore Agent.
    
    Loads settings from config.yml in the project root.
    """
    
    def __init__(self):
        self._config = self._load_config()
        self._update_config = self._load_update_config()

    def _load_config(self) -> dict:
        """Load main configuration file."""
        config_path = Path(__file__).parent.parent.parent / "config.yml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def _load_update_config(self) -> dict:
        """Load update configuration file (optional)."""
        # Try multiple locations
        possible_paths = [
            Path(__file__).parent.parent.parent / "updater" / "update_config.yml",
            Path(__file__).parent.parent.parent / "update_config.yml",
        ]
        
        for config_path in possible_paths:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    data = yaml.safe_load(f)
                    return data.get("updates", {}) if data else {}
        
        # Return defaults if no config found
        return {}

    # =========================================================================
    # Main Config Properties
    # =========================================================================

    @property
    def central_api_url(self) -> str:
        return self._config.get("centralApiUrl", "ws://localhost:8000/agent/ws")

    @property
    def log_level(self) -> str:
        return self._config.get("logLevel", "INFO")

    @property
    def max_reconnect_attempts(self) -> int:
        return self._config.get("maxReconnectAttempts", 8)

    @property
    def reconnect_delay_sec(self) -> int:
        return self._config.get("reconnectDelaySec", 5)

    # =========================================================================
    # Update Config Properties
    # =========================================================================

    @property
    def updates_enabled(self) -> bool:
        return self._update_config.get("enabled", True)

    @property
    def auto_apply_forced(self) -> bool:
        return self._update_config.get("autoApplyForced", True)

    @property
    def check_updates_on_startup(self) -> bool:
        return self._update_config.get("checkOnStartup", True)

    @property
    def show_update_notifications(self) -> bool:
        return self._update_config.get("showNotifications", True)

    @property
    def keep_rollback(self) -> bool:
        return self._update_config.get("keepRollback", True)


# Singleton instance
config = Config()
