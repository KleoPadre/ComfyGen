from __future__ import annotations

from comfygen.models import DeviceInfo, Template

# Схемы квантования, для которых PyTorch не реализует нужные операции на
# бэкенде MPS (Apple Silicon) — попытка запуска гарантированно упадёт с
# NotImplementedError (например, torch._int_mm для int8), независимо от
# объёма доступной памяти. На CUDA/Triton эти же модели работают штатно.
MPS_INCOMPATIBLE_KEYWORDS = {
    "int8",
    "nvfp4",
    "mxfp8",
    "svdquant",
    "convrot",
    "awq",
}


def _mentions_any(template: Template, keywords: set[str]) -> bool:
    haystack = " ".join([template.name, template.title, *template.models]).lower()
    return any(keyword in haystack for keyword in keywords)


def filter_device_incompatible(templates: list[Template], device: DeviceInfo) -> list[Template]:
    """Исключить шаблоны, требующие операций, не реализованных для типа
    устройства пользователя. Пока покрывает единственный известный случай:
    INT8/NVFP4/MXFP8-квантованные модели не запускаются на MPS."""
    if device.device_type != "mps":
        return templates
    return [t for t in templates if not _mentions_any(t, MPS_INCOMPATIBLE_KEYWORDS)]
