import os
import time

import httpx
import respx

from comfygen.catalog import (
    INDEX_URL,
    fetch_remote_index,
    get_index,
    load_cached_index,
    save_cache,
)

SAMPLE_RAW_INDEX = [
    {
        "type": "image",
        "title": "Image",
        "templates": [
            {
                "name": "image_z_image_turbo",
                "title": "Z-Image-Turbo: Text to Image",
                "tags": ["Image", "Text to Image"],
                "models": ["Z-Image-Turbo"],
                "vram": 20830591386,
                "size": 20830591386,
                "description": "desc",
            },
        ],
    },
    {
        "type": "video",
        "title": "Video",
        "templates": [
            {
                "name": "video_ltx2_3_i2v",
                "title": "LTX-2.3: Image to Video",
                "tags": ["Image to Video", "Video"],
                "models": ["LTX-2.3"],
                "vram": 47244640256,
                "size": 47244640256,
                "description": "desc",
            },
            {
                "name": "video_wan_t2v",
                "title": "WAN: Text to Video",
                "tags": ["Text to Video", "Video"],
                "models": ["WAN"],
                "vram": 17179869184,
                "size": 17179869184,
                "description": "desc",
            },
        ],
    },
    {
        "type": "audio",
        "title": "Audio",
        "templates": [
            {
                "name": "audio_ace_step",
                "title": "ACE-Step: Text to Audio",
                "tags": ["Text to Audio", "Audio"],
                "models": ["ACE-Step"],
                "size": 5368709120,
                "description": "no vram field",
            },
        ],
    },
]


@respx.mock
def test_fetch_remote_index_returns_parsed_json():
    respx.get(INDEX_URL).mock(return_value=httpx.Response(200, json=SAMPLE_RAW_INDEX))
    with httpx.Client() as client:
        result = fetch_remote_index(client)
    assert result == SAMPLE_RAW_INDEX


def test_load_cached_index_missing_file_returns_none(tmp_path):
    cache_path = tmp_path / "cache.json"
    assert load_cached_index(cache_path, ttl_seconds=3600) is None


def test_save_and_load_cache_round_trip(tmp_path):
    cache_path = tmp_path / "sub" / "cache.json"
    save_cache(cache_path, SAMPLE_RAW_INDEX)
    loaded = load_cached_index(cache_path, ttl_seconds=3600)
    assert loaded == SAMPLE_RAW_INDEX


def test_load_cached_index_expired_returns_none(tmp_path):
    cache_path = tmp_path / "cache.json"
    save_cache(cache_path, SAMPLE_RAW_INDEX)
    old_time = time.time() - 3700
    os.utime(cache_path, (old_time, old_time))
    assert load_cached_index(cache_path, ttl_seconds=3600) is None


def test_load_cached_index_corrupted_json_returns_none(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text("not valid json{", encoding="utf-8")
    assert load_cached_index(cache_path, ttl_seconds=3600) is None


@respx.mock
def test_get_index_uses_cache_when_fresh(tmp_path):
    cache_path = tmp_path / "cache.json"
    save_cache(cache_path, SAMPLE_RAW_INDEX)
    route = respx.get(INDEX_URL).mock(return_value=httpx.Response(200, json=[]))
    with httpx.Client() as client:
        result = get_index(client, cache_path, ttl_seconds=3600)
    assert result == SAMPLE_RAW_INDEX
    assert route.call_count == 0


@respx.mock
def test_get_index_force_refresh_ignores_cache(tmp_path):
    cache_path = tmp_path / "cache.json"
    save_cache(cache_path, SAMPLE_RAW_INDEX)
    new_data = [{"type": "image", "title": "Image", "templates": []}]
    respx.get(INDEX_URL).mock(return_value=httpx.Response(200, json=new_data))
    with httpx.Client() as client:
        result = get_index(client, cache_path, ttl_seconds=3600, force_refresh=True)
    assert result == new_data


from comfygen.catalog import filter_by_generation_type, parse_templates
from comfygen.models import GenerationType


def test_parse_templates_flattens_all_categories():
    templates = parse_templates(SAMPLE_RAW_INDEX)
    assert len(templates) == 4
    names = {t.name for t in templates}
    assert names == {
        "image_z_image_turbo",
        "video_ltx2_3_i2v",
        "video_wan_t2v",
        "audio_ace_step",
    }
    audio_template = next(t for t in templates if t.name == "audio_ace_step")
    assert audio_template.vram_bytes is None
    assert audio_template.category == "audio"


def test_filter_by_generation_type_photo():
    templates = parse_templates(SAMPLE_RAW_INDEX)
    result = filter_by_generation_type(templates, GenerationType.PHOTO)
    assert [t.name for t in result] == ["image_z_image_turbo"]


def test_filter_by_generation_type_video_excludes_image_to_video():
    templates = parse_templates(SAMPLE_RAW_INDEX)
    result = filter_by_generation_type(templates, GenerationType.VIDEO)
    assert [t.name for t in result] == ["video_wan_t2v"]


def test_filter_by_generation_type_animate_photo_is_image_to_video():
    templates = parse_templates(SAMPLE_RAW_INDEX)
    result = filter_by_generation_type(templates, GenerationType.ANIMATE_PHOTO)
    assert [t.name for t in result] == ["video_ltx2_3_i2v"]


def test_filter_by_generation_type_audio():
    templates = parse_templates(SAMPLE_RAW_INDEX)
    result = filter_by_generation_type(templates, GenerationType.AUDIO)
    assert [t.name for t in result] == ["audio_ace_step"]
