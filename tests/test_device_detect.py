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
