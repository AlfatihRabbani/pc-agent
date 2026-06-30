"""Load and access config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


class Config:
    def __init__(self, data: dict[str, Any]):
        self._d = data

    def __getitem__(self, key: str) -> Any:
        return self._d[key]

    def get(self, dotted: str, default: Any = None) -> Any:
        """cfg.get('brain.model_id') -> nested lookup."""
        node: Any = self._d
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def path(self, dotted: str, default: str = "") -> Path:
        """Resolve a config value to an absolute path under the project root."""
        val = self.get(dotted, default)
        p = Path(val)
        return p if p.is_absolute() else (ROOT / p)


def load(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    with open(path, "r", encoding="utf-8") as f:
        return Config(yaml.safe_load(f))
