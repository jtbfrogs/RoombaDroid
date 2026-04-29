"""JSON configuration with dot-notation access and in-memory caching."""
import json
from pathlib import Path
from typing import Any, Dict, Optional


class Config:
    """Loads config.json on startup and provides cached dot-notation reads.

    Example:
        config.get("roomba.uart_port")          # -> "COM7"
        config.set("vision.frame_skip", 3)      # persists to disk
    """

    def __init__(self, config_file: str = "config.json") -> None:
        self._config: Dict[str, Any] = {}
        self._cache: Dict[str, Any] = {}
        self.config_file = Path(config_file)
        self._load()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.config_file.exists():
            self._config = self._defaults()
            self._save()
        else:
            with self.config_file.open() as f:
                self._config = json.load(f)

    def _save(self) -> None:
        with self.config_file.open("w") as f:
            json.dump(self._config, f, indent=2)

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def _defaults(self) -> Dict[str, Any]:
        return {
            "droid": {
                "name": "D O",
                "personality": "shy, loyal, awkward droid",
            },
            "roomba": {
                "uart_port": "COM7",
                "baud_rate": 115200,
                "use_rts_cts": True,
                "wakeup_wait_time": 0.5,
                "velocity": 200,
                "spin_velocity": 100,
                "max_velocity": 500,
                "watchdog_timeout": 2.0,
                "connection_timeout": 3.0,
            },
            "vision": {
                "camera_index": 0,
                "frame_width": 640,
                "frame_height": 480,
                "fps": 30,
                "frame_skip": 2,
                "min_detection_confidence": 0.5,
            },
            "voice": {
                "recognizer_energy_threshold": 300,
                "recognizer_pause_threshold": 0.8,
                "tts_rate": 230,
                "tts_volume": 1.0,
                "language": "en-US",
            },
            "llm": {
                "model": "neural-chat",
            },
            "lights": {
                "enabled": False,
                "govee_api_key": "",
                "govee_device_id": "",
            },
            "performance": {
                "worker_threads": 5,
                "command_queue_size": 50,
                "enable_profiling": False,
            },
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        """Return a value by dot-notation path, e.g. ``'roomba.uart_port'``."""
        if path in self._cache:
            return self._cache[path]

        node = self._config
        for key in path.split("."):
            if not isinstance(node, dict):
                return default
            node = node.get(key)
            if node is None:
                return default

        self._cache[path] = node
        return node

    def set(self, path: str, value: Any) -> None:
        """Set a value by dot-notation path and persist to disk."""
        keys = path.split(".")
        node = self._config
        for key in keys[:-1]:
            node = node.setdefault(key, {})
        node[keys[-1]] = value
        self._cache.pop(path, None)  # invalidate cached entry
        self._save()


# Module-level singleton
config = Config("config.json")
