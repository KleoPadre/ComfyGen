from comfygen.models import DeviceInfo, Template, VramTier
from comfygen.vram_filter import classify_template, classify_templates

DEVICE = DeviceInfo(available_vram_bytes=16 * 1024**3, device_type="cuda", source="os")


def make_template(name: str, vram_bytes: int | None) -> Template:
    return Template(
        name=name,
        title=name,
        category="image",
        tags=[],
        models=[],
        vram_bytes=vram_bytes,
        size_bytes=vram_bytes,
        description="",
    )


def test_classify_template_safe_when_well_within_budget():
    t = make_template("safe", vram_bytes=10 * 1024**3)
    assert classify_template(t, DEVICE, safe_factor=0.9, warning_factor=1.15) == VramTier.SAFE


def test_classify_template_warning_when_slightly_over_safe_threshold():
    t = make_template("warn", vram_bytes=15 * 1024**3)
    assert classify_template(t, DEVICE, safe_factor=0.9, warning_factor=1.15) == VramTier.WARNING


def test_classify_template_hidden_when_far_over_budget():
    t = make_template("hidden", vram_bytes=25 * 1024**3)
    assert classify_template(t, DEVICE, safe_factor=0.9, warning_factor=1.15) == VramTier.HIDDEN


def test_classify_template_unknown_when_vram_missing():
    t = make_template("unknown", vram_bytes=None)
    assert classify_template(t, DEVICE, safe_factor=0.9, warning_factor=1.15) == VramTier.UNKNOWN


def test_classify_templates_groups_by_tier():
    templates = [
        make_template("safe", 10 * 1024**3),
        make_template("warn", 15 * 1024**3),
        make_template("hidden", 25 * 1024**3),
        make_template("unknown", None),
    ]
    result = classify_templates(templates, DEVICE, safe_factor=0.9, warning_factor=1.15)
    assert [t.name for t in result[VramTier.SAFE]] == ["safe"]
    assert [t.name for t in result[VramTier.WARNING]] == ["warn"]
    assert [t.name for t in result[VramTier.HIDDEN]] == ["hidden"]
    assert [t.name for t in result[VramTier.UNKNOWN]] == ["unknown"]
