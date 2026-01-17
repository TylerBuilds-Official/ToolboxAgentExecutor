import yaml
from pathlib import Path


class Config:
    def __init__(self):
        self._config = self._load_config()

    def _load_config(self) -> dict:
        config_path = Path(__file__).parent.parent.parent / "config.yml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

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


# Singleton
config = Config()
