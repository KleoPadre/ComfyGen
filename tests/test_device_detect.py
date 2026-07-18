import pytest

from comfygen.device_detect import UnsupportedPlatformError, _query_nvidia_smi_vram, detect_via_os


class FakeVirtualMemory:
    def __init__(self, total: int):
        self.total = total


def test_detect_via_os_apple_silicon(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Darwin")
    monkeypatch.setattr("comfygen.device_detect.platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "comfygen.device_detect.psutil.virtual_memory",
        lambda: FakeVirtualMemory(total=32 * 1024**3),
    )
    info = detect_via_os(apple_unified_memory_factor=0.7)
    assert info.device_type == "mps"
    assert info.source == "os"
    assert info.available_vram_bytes == int(32 * 1024**3 * 0.7)


def test_detect_via_os_intel_mac_returns_cpu_fallback(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Darwin")
    monkeypatch.setattr("comfygen.device_detect.platform.machine", lambda: "x86_64")
    info = detect_via_os()
    assert info.device_type == "cpu"
    assert info.available_vram_bytes == 0


def test_detect_via_os_windows_with_nvidia_gpu(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "comfygen.device_detect._query_nvidia_smi_vram", lambda: 24576 * 1024 * 1024
    )
    info = detect_via_os()
    assert info.device_type == "cuda"
    assert info.available_vram_bytes == 24576 * 1024 * 1024


def test_detect_via_os_windows_without_nvidia_gpu(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Windows")
    monkeypatch.setattr("comfygen.device_detect._query_nvidia_smi_vram", lambda: None)
    info = detect_via_os()
    assert info.device_type == "cpu"
    assert info.available_vram_bytes == 0


def test_detect_via_os_unsupported_platform_raises(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Linux")
    with pytest.raises(UnsupportedPlatformError):
        detect_via_os()


def test_query_nvidia_smi_vram_parses_output(monkeypatch):
    class FakeCompletedProcess:
        stdout = "24576\n"

    def fake_run(*args, **kwargs):
        return FakeCompletedProcess()

    monkeypatch.setattr("comfygen.device_detect.subprocess.run", fake_run)
    assert _query_nvidia_smi_vram() == 24576 * 1024 * 1024


def test_query_nvidia_smi_vram_returns_none_when_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("comfygen.device_detect.subprocess.run", fake_run)
    assert _query_nvidia_smi_vram() is None


from comfygen.device_detect import detect_hybrid, detect_via_api


class FakeComfyClient:
    def __init__(self, healthy: bool, stats: dict):
        self._healthy = healthy
        self._stats = stats

    def health_check(self, timeout: float = 2.0) -> bool:
        return self._healthy

    def system_stats(self) -> dict:
        return self._stats


def test_detect_via_api_parses_first_device():
    client = FakeComfyClient(healthy=True, stats={"devices": [{"type": "cuda", "vram_total": 25757220864}]})
    info = detect_via_api(client)
    assert info.device_type == "cuda"
    assert info.available_vram_bytes == 25757220864
    assert info.source == "api"


def test_detect_hybrid_uses_api_when_healthy():
    client = FakeComfyClient(healthy=True, stats={"devices": [{"type": "mps", "vram_total": 17179869184}]})
    info = detect_hybrid(client)
    assert info.source == "hybrid-api"
    assert info.available_vram_bytes == 17179869184


def test_detect_hybrid_falls_back_to_os_when_unhealthy(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Darwin")
    monkeypatch.setattr("comfygen.device_detect.platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "comfygen.device_detect.psutil.virtual_memory",
        lambda: FakeVirtualMemory(total=16 * 1024**3),
    )
    client = FakeComfyClient(healthy=False, stats={})
    info = detect_hybrid(client, apple_unified_memory_factor=0.7)
    assert info.source == "hybrid-os"
