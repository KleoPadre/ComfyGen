from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from comfygen.models import GenerationType, Template

INDEX_URL = "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/index.json"
TEMPLATE_FILE_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/{name}.json"
)


def fetch_remote_index(client: httpx.Client) -> list[dict]:
    response = client.get(INDEX_URL, timeout=15.0)
    response.raise_for_status()
    return response.json()


def fetch_remote_template(client: httpx.Client, name: str) -> dict:
    response = client.get(TEMPLATE_FILE_URL_TEMPLATE.format(name=name), timeout=15.0)
    response.raise_for_status()
    return response.json()


def load_cached_index(cache_path: Path, ttl_seconds: int) -> list[dict] | None:
    if not cache_path.exists():
        return None
    age = time.time() - cache_path.stat().st_mtime
    if age > ttl_seconds:
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_cache(cache_path: Path, raw_index: list[dict]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(raw_index), encoding="utf-8")


def get_index(
    client: httpx.Client,
    cache_path: Path,
    ttl_seconds: int,
    force_refresh: bool = False,
) -> list[dict]:
    if not force_refresh:
        cached = load_cached_index(cache_path, ttl_seconds)
        if cached is not None:
            return cached
    raw_index = fetch_remote_index(client)
    save_cache(cache_path, raw_index)
    return raw_index


def parse_templates(raw_index: list[dict]) -> list[Template]:
    templates: list[Template] = []
    for group in raw_index:
        category = group.get("type", "unknown")
        for t in group.get("templates", []):
            templates.append(
                Template(
                    name=t["name"],
                    title=t.get("title", t["name"]),
                    category=category,
                    tags=t.get("tags", []),
                    models=t.get("models", []),
                    vram_bytes=t.get("vram"),
                    size_bytes=t.get("size"),
                    description=t.get("description", ""),
                    open_source=bool(t.get("openSource", True)),
                )
            )
    return templates


def filter_by_generation_type(templates: list[Template], gen_type: GenerationType) -> list[Template]:
    """Только локальные шаблоны (open_source) — облачные/платные API-ноды
    (openSource: false в каталоге Comfy) никогда не предлагаются: они не
    выполняются на устройстве пользователя и требуют логина/оплаты."""
    templates = [t for t in templates if t.open_source]
    if gen_type == GenerationType.PHOTO:
        return [t for t in templates if t.category == "image" and "Text to Image" in t.tags]
    if gen_type == GenerationType.AUDIO:
        return [t for t in templates if t.category == "audio"]
    if gen_type == GenerationType.VIDEO:
        return [t for t in templates if t.category == "video" and "Image to Video" not in t.tags]
    if gen_type == GenerationType.ANIMATE_PHOTO:
        return [t for t in templates if t.category == "video" and "Image to Video" in t.tags]
    raise ValueError(f"Неизвестный тип генерации: {gen_type}")
