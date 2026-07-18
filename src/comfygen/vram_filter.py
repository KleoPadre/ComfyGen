from __future__ import annotations

from comfygen.models import DeviceInfo, Template, VramTier


def classify_template(
    template: Template,
    device: DeviceInfo,
    safe_factor: float,
    warning_factor: float,
) -> VramTier:
    if template.vram_bytes is None:
        return VramTier.UNKNOWN
    safe_limit = device.available_vram_bytes * safe_factor
    warning_limit = device.available_vram_bytes * warning_factor
    if template.vram_bytes <= safe_limit:
        return VramTier.SAFE
    if template.vram_bytes <= warning_limit:
        return VramTier.WARNING
    return VramTier.HIDDEN


def classify_templates(
    templates: list[Template],
    device: DeviceInfo,
    safe_factor: float,
    warning_factor: float,
) -> dict[VramTier, list[Template]]:
    result: dict[VramTier, list[Template]] = {tier: [] for tier in VramTier}
    for template in templates:
        tier = classify_template(template, device, safe_factor, warning_factor)
        result[tier].append(template)
    return result
