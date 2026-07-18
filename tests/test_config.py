from comfygen.config import Config, DEFAULT_COMFY_BASE_URL, load_config, save_config


def test_load_config_returns_defaults_when_file_missing(tmp_path):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    assert config.comfy_base_url == DEFAULT_COMFY_BASE_URL
    assert config.vram_safe_factor == 0.9
    assert config.vram_warning_factor == 1.15


def test_save_and_load_config_round_trip(tmp_path):
    config_path = tmp_path / "nested" / "config.json"
    original = Config(comfy_base_url="http://localhost:9000", vram_safe_factor=0.8)
    save_config(original, config_path)
    loaded = load_config(config_path)
    assert loaded == original
