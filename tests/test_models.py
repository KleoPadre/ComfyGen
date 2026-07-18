from comfygen.models import DeviceInfo, GenerationType, Template, VramTier


def test_generation_type_values():
    assert {t.value for t in GenerationType} == {"photo", "video", "audio", "animate_photo"}


def test_vram_tier_values():
    assert {t.value for t in VramTier} == {"safe", "warning", "hidden", "unknown"}


def test_template_construction():
    t = Template(
        name="image_z_image_turbo",
        title="Z-Image-Turbo",
        category="image",
        tags=["Text to Image"],
        models=["Z-Image-Turbo"],
        vram_bytes=20830591386,
        size_bytes=20830591386,
        description="desc",
    )
    assert t.name == "image_z_image_turbo"
    assert t.vram_bytes == 20830591386


def test_device_info_construction():
    d = DeviceInfo(available_vram_bytes=16 * 1024**3, device_type="cuda", source="os")
    assert d.device_type == "cuda"
