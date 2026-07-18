from __future__ import annotations

import platform
import subprocess
from typing import Protocol

import psutil

from comfygen.config import DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR
from comfygen.models import DeviceInfo


class SupportsSystemStats(Protocol):
    def health_check(self, timeout: float = ...) -> bool: ...
    def system_stats(self) -> dict: ...


class UnsupportedPlatformError(RuntimeError):
    pass


class DeviceDetectionError(RuntimeError):
    pass


def detect_via_os(
    apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR,
) -> DeviceInfo:
    system = platform.system()
    if system == "Darwin":
        return _detect_macos(apple_unified_memory_factor)
    if system == "Windows":
        return _detect_windows()
    raise UnsupportedPlatformError(f"Платформа {system} не поддерживается для детекции через ОС")


def _detect_macos(apple_unified_memory_factor: float) -> DeviceInfo:
    if platform.machine() == "arm64":
        total_ram = psutil.virtual_memory().total
        return DeviceInfo(
            available_vram_bytes=int(total_ram * apple_unified_memory_factor),
            device_type="mps",
            source="os",
        )
    return DeviceInfo(available_vram_bytes=0, device_type="cpu", source="os")


def _detect_windows() -> DeviceInfo:
    vram = _query_nvidia_smi_vram()
    if vram is not None:
        return DeviceInfo(available_vram_bytes=vram, device_type="cuda", source="os")
    return DeviceInfo(available_vram_bytes=0, device_type="cpu", source="os")


def _query_nvidia_smi_vram() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    first_line = result.stdout.strip().splitlines()[0]
    return int(first_line.strip()) * 1024 * 1024


def detect_via_api(client: SupportsSystemStats) -> DeviceInfo:
    stats = client.system_stats()
    devices = stats.get("devices") or []
    if not devices:
        raise DeviceDetectionError("ComfyUI /system_stats вернул пустой список устройств")
    device = devices[0]
    return DeviceInfo(
        available_vram_bytes=int(device.get("vram_total", 0)),
        device_type=device.get("type", "unknown"),
        source="api",
    )


def detect_hybrid(
    client: SupportsSystemStats,
    apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR,
) -> DeviceInfo:
    if client.health_check():
        info = detect_via_api(client)
        return DeviceInfo(info.available_vram_bytes, info.device_type, source="hybrid-api")
    info = detect_via_os(apple_unified_memory_factor)
    return DeviceInfo(info.available_vram_bytes, info.device_type, source="hybrid-os")
