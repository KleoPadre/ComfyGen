from comfygen.device_compatibility import filter_device_incompatible
from comfygen.models import DeviceInfo, Template

MPS_DEVICE = DeviceInfo(available_vram_bytes=16 * 1024**3, device_type="mps", source="os")
CUDA_DEVICE = DeviceInfo(available_vram_bytes=16 * 1024**3, device_type="cuda", source="os")


def make_template(name: str, title: str = "", models: list[str] | None = None) -> Template:
    return Template(name=name, title=title or name, category="image", models=models or [])


def test_filter_device_incompatible_excludes_int8_on_mps():
    templates = [
        make_template("image_z_image_base_int8", models=["z_image_int8_convrot.safetensors"]),
        make_template("image_z_image_turbo"),
    ]
    result = filter_device_incompatible(templates, MPS_DEVICE)
    assert [t.name for t in result] == ["image_z_image_turbo"]


def test_filter_device_incompatible_keeps_everything_on_cuda():
    templates = [
        make_template("image_z_image_base_int8", models=["z_image_int8_convrot.safetensors"]),
        make_template("image_z_image_turbo"),
    ]
    result = filter_device_incompatible(templates, CUDA_DEVICE)
    assert len(result) == 2


def test_filter_device_incompatible_matches_by_model_name_not_just_template_name():
    templates = [make_template("some_template", models=["model_nvfp4_variant.safetensors"])]
    result = filter_device_incompatible(templates, MPS_DEVICE)
    assert result == []


def test_filter_device_incompatible_keeps_unrelated_templates_on_mps():
    templates = [make_template("image_z_image_turbo", models=["z_image_turbo_bf16.safetensors"])]
    result = filter_device_incompatible(templates, MPS_DEVICE)
    assert len(result) == 1
