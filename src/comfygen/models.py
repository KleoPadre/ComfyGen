from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GenerationType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    ANIMATE_PHOTO = "animate_photo"


class VramTier(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    HIDDEN = "hidden"
    UNKNOWN = "unknown"


@dataclass
class Template:
    name: str
    title: str
    category: str
    tags: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    vram_bytes: int | None = None
    size_bytes: int | None = None
    description: str = ""
    open_source: bool = True


@dataclass
class DeviceInfo:
    available_vram_bytes: int
    device_type: str
    source: str
