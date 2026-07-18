from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_COMFY_BASE_URL = "http://127.0.0.1:8188"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_VRAM_SAFE_FACTOR = 0.9
DEFAULT_VRAM_WARNING_FACTOR = 1.15
DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR = 0.7

CONFIG_DIR = Path.home() / ".comfygen"
CONFIG_PATH = CONFIG_DIR / "config.json"
CACHE_PATH = CONFIG_DIR / "templates_index_cache.json"


@dataclass
class Config:
    comfy_base_url: str = DEFAULT_COMFY_BASE_URL
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    vram_safe_factor: float = DEFAULT_VRAM_SAFE_FACTOR
    vram_warning_factor: float = DEFAULT_VRAM_WARNING_FACTOR
    apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(**data)


def save_config(config: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
