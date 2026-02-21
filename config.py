import json
import os
from typing import Any, Dict, Optional

class ConfigReader:
    DEFAULT_CONFIG: Dict[str, Any] = {
        "model_path": "",
        "sound_device_index": "",
        "sample_rate": 16000
    }

    def __init__(self, path: str = "config.json"):
        self.config_path = path
        self.current_config: Dict[str, Any] = self._load_config()

        if not os.path.isfile(self.config_path):
            self._write_config(self.current_config)

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            return dict(self.DEFAULT_CONFIG)

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cfg = dict(self.DEFAULT_CONFIG)
            if isinstance(data, dict):
                for k in self.DEFAULT_CONFIG.keys():
                    if k in data:
                        cfg[k] = data[k]
            return cfg
        except Exception:
            return dict(self.DEFAULT_CONFIG)

    def _write_config(self, cfg: Dict[str, Any]) -> None:
        tmp = self.config_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        os.replace(tmp, self.config_path)

    def save_config(self, cfg: Dict[str, Any]) -> None:
        out = dict(self.DEFAULT_CONFIG)
        for k in self.DEFAULT_CONFIG.keys():
            if k in cfg and cfg[k] is not None:
                out[k] = cfg[k]

        self._write_config(out)
        self.current_config = out

    def get_value(self, key: str, default: Any = None) -> Any:
        if key not in self.DEFAULT_CONFIG:
            return default
        return self.current_config.get(key, default)

    def update_value(self, key: str, value: Any) -> None:
        if key not in self.DEFAULT_CONFIG:
            raise KeyError(f"Unknown config key: {key}")

        self.current_config[key] = value
        self.save_config(self.current_config)

    def update_many(self, updates: Dict[str, Any]) -> None:
        for k, v in updates.items():
            if k not in self.DEFAULT_CONFIG:
                raise KeyError(f"Unknown config key: {k}")
            self.current_config[k] = v
        self.save_config(self.current_config)