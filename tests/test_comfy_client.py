import json

import httpx
import pytest
import respx

from comfygen.comfy_client import ComfyClient

BASE_URL = "http://127.0.0.1:8188"


@respx.mock
def test_health_check_true_on_200():
    respx.get(f"{BASE_URL}/system_stats").mock(return_value=httpx.Response(200, json={}))
    client = ComfyClient(BASE_URL)
    assert client.health_check() is True


@respx.mock
def test_health_check_false_on_connection_error():
    respx.get(f"{BASE_URL}/system_stats").mock(side_effect=httpx.ConnectError("refused"))
    client = ComfyClient(BASE_URL)
    assert client.health_check() is False


@respx.mock
def test_system_stats_returns_parsed_json():
    payload = {"devices": [{"type": "cuda", "vram_total": 123}]}
    respx.get(f"{BASE_URL}/system_stats").mock(return_value=httpx.Response(200, json=payload))
    client = ComfyClient(BASE_URL)
    assert client.system_stats() == payload


@respx.mock
def test_upload_image_returns_server_filename(tmp_path):
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"fake-image-bytes")
    respx.post(f"{BASE_URL}/upload/image").mock(
        return_value=httpx.Response(200, json={"name": "photo.png", "subfolder": "", "type": "input"})
    )
    client = ComfyClient(BASE_URL)
    assert client.upload_image(image_path) == "photo.png"


@respx.mock
def test_save_workflow_posts_workflow_json():
    route = respx.post(url__startswith=f"{BASE_URL}/userdata/").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    client = ComfyClient(BASE_URL)
    client.save_workflow("my_generation.json", {"nodes": []})
    assert route.call_count == 1
    assert json.loads(route.calls[0].request.content) == {"nodes": []}


@respx.mock
def test_save_workflow_raises_on_http_error():
    respx.post(url__startswith=f"{BASE_URL}/userdata/").mock(return_value=httpx.Response(500))
    client = ComfyClient(BASE_URL)
    with pytest.raises(httpx.HTTPStatusError):
        client.save_workflow("my_generation.json", {"nodes": []})
