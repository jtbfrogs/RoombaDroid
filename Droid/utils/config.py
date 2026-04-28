"""Optimized configuration management with validation."""
import json
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    """Fast configuration manager with caching."""
    
    def __init__(self, config_file: str = "config.json"):
        self._config: Dict[str, Any] = {}
        self._cache: Dict[str, Any] = {}
        self.config_file = Path(config_file)
        self._load()
    
    def _load(self):
        """Load configuration from file."""
        if not self.config_file.exists():
            self._config = self._get_defaults()
            self._save()
        else:
            with open(self.config_file) as f:
                self._config = json.load(f)
    
    def _save(self):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            json.dump(self._config, f, indent=2)
    
    def _get_defaults(self) -> Dict:
        """Get default configuration."""
        return {
            "droid": {
                "name": "D O",
                "personality": "shy, loyal, awkward droid"
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
                "connection_timeout": 3.0
            },
            "vision": {
                "camera_index": 0,
                "frame_width": 640,
                "frame_height": 480,
                "fps": 30,
                "frame_skip": 2,
                "min_detection_confidence": 0.5
            },
            "voice": {
                "recognizer_energy_threshold": 300,
                "recognizer_pause_threshold": 2.3,
                "tts_rate": 230,
                "tts_volume": 1.0,
                "language": "en-US"
            },
            "lights": {
                "enabled": False,
                "govee_api_key": "",
                "govee_device_id": ""
            },
            "performance": {
                "worker_threads": 3,
                "command_queue_size": 50,
                "enable_profiling": False
            }
        }
    
    def get(self, path: str, default: Any = None) -> Any:
        """Get config value with dot notation."""
        if path in self._cache:
            return self._cache[path]
        
        parts = path.split('.')
        value = self._config
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None:
                    return default
            else:
                return default
        
        self._cache[path] = value
        return value
    
    def set(self, path: str, value: Any):
        """Set config value with dot notation."""
        parts = path.split('.')
        config = self._config
        
        for part in parts[:-1]:
            if part not in config:
                config[part] = {}
            config = config[part]
        
        config[parts[-1]] = value
        self._cache.pop(path, None)  # Invalidate cache
        self._save()

# Global instance
config = Config("config.json")
