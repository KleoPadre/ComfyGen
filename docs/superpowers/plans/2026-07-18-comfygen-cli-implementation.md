# ComfyGen CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Реализовать автономный Python CLI-инструмент ComfyGen, который проводит пользователя от выбора типа генерации до готового workflow-файла в ComfyUI, отфильтровав модели по реальным VRAM-требованиям устройства.

**Architecture:** Слоистая структура пакета `comfygen`: чистые модули без побочных эффектов (`models`, `vram_filter`, `workflow_editor`, часть `catalog`) покрываются юнит-тестами напрямую; модули с внешними эффектами (`comfy_client`, `catalog` — сетевые вызовы, `device_detect` — вызовы ОС) тестируются через моки (`respx` для HTTP, `monkeypatch` для `platform`/`psutil`/`subprocess`); интерактивный UI-слой (`ui.py`) и точка входа (`__main__.py`) — тонкие обёртки без сложной логики, проверяются вручную. Ключевая техническая находка: официальные workflow-шаблоны Comfy часто «subgraph»-ированы — нужные узлы (CLIPTextEncode, KSampler, EmptyLatentImage, LoadImage) лежат не только в `workflow["nodes"]`, но и внутри `workflow["definitions"]["subgraphs"][*]["nodes"]`, поэтому весь код редактирования workflow обязан обходить оба места.

**Tech Stack:** Python ≥3.10, `httpx` (HTTP-клиент), `rich` + `questionary` (интерактивный CLI), `psutil` (системная информация), `pytest` + `respx` + `pytest-mock` (тесты), `hatchling` (сборка).

## Global Constraints

- Целевые платформы: macOS (основная) и Windows (обязательна поддержка) — спецификация, раздел «Назначение».
- Источник данных о моделях: `Comfy-Org/workflow_templates`, файлы `templates/index.json` и `templates/<name>.json`, без собственной VRAM-таблицы — спецификация, раздел «Источник данных о моделях».
- Локальный кеш `index.json` с TTL ~24 часа и флагом принудительного обновления — спецификация, раздел «Поток выполнения», п. 3.
- VRAM-тиры: Safe при `vram ≤ available × 0.9`, Warning при `available × 0.9 < vram ≤ available × 1.15`, иначе Hidden; коэффициенты вынесены в конфиг — спецификация, раздел «Фильтрация моделей по VRAM».
- Сохранение результата — единственный способ: `POST /userdata/workflows/<file>.json` в запущенный ComfyUI — спецификация, раздел «Сохранение результата».
- Установка не требует от пользователя ручного `pip install` — `run.sh`/`run.bat` сами создают venv и ставят зависимости — спецификация, раздел «Установка и запуск».
- Все тексты интерфейса (вопросы, подсказки, сообщения об ошибках) — на русском языке (следует из языка всей переписки и проекта; при желании можно сделать конфигурируемым позже, но не в v1).

---

## Task 1: Каркас проекта и модуль конфигурации

**Files:**
- Modify: `pyproject.toml`
- Create: `src/comfygen/__init__.py`
- Create: `src/comfygen/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `comfygen.config.Config` (dataclass), `comfygen.config.load_config(path: Path = CONFIG_PATH) -> Config`, `comfygen.config.save_config(config: Config, path: Path = CONFIG_PATH) -> None`, константы `DEFAULT_COMFY_BASE_URL`, `DEFAULT_CACHE_TTL_SECONDS`, `DEFAULT_VRAM_SAFE_FACTOR`, `DEFAULT_VRAM_WARNING_FACTOR`, `DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR`, `CONFIG_DIR`, `CONFIG_PATH`, `CACHE_PATH`.

- [ ] **Step 1: Обновить `pyproject.toml`**

Заменить содержимое файла на:

```toml
[project]
name = "comfygen"
version = "0.1.0"
description = "CLI-помощник для генерации в ComfyUI"
authors = [
    { name = "Levon Osipov", email = "osipoff.levon@gmail.com" }
]
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
dependencies = [
    "httpx>=0.27",
    "rich>=13.7",
    "questionary>=2.0",
    "psutil>=5.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
    "respx>=0.21",
]

[project.scripts]
comfygen = "comfygen.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/comfygen"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Создать пакет и файл-заглушку версии**

`src/comfygen/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Написать падающий тест для config.py**

`tests/test_config.py`:

```python
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
```

- [ ] **Step 4: Установить проект в editable-режиме и убедиться, что тест падает**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.config'`

- [ ] **Step 5: Реализовать `config.py`**

`src/comfygen/config.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_COMFY_BASE_URL = "http://127.0.0.1:8188"
DEFAULT_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_VRAM_SAFE_FACTOR = 0.9
DEFAULT_VRAM_WARNING_FACTOR = 1.15
DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR = 0.7

CONFIG_DIR = Path.home() / ".comfygen"
CONFIG_PATH = CONFIG_DIR / "config.json"
CACHE_PATH = CONFIG_DIR / "templates_index_cache.json"


@dataclass
class Config:
    comfy_base_url: str = DEFAULT_COMFY_BASE_URL
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    vram_safe_factor: float = DEFAULT_VRAM_SAFE_FACTOR
    vram_warning_factor: float = DEFAULT_VRAM_WARNING_FACTOR
    apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(**data)


def save_config(config: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 6: Прогнать тесты и убедиться, что проходят**

```bash
pytest tests/test_config.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 7: Коммит**

```bash
git add pyproject.toml src/comfygen/__init__.py src/comfygen/config.py tests/test_config.py
git commit -m "feat: каркас проекта и модуль конфигурации"
```

---

## Task 2: Модели данных

**Files:**
- Create: `src/comfygen/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: ничего (базовый модуль).
- Produces: `GenerationType(str, Enum)` со значениями `PHOTO="photo"`, `VIDEO="video"`, `AUDIO="audio"`, `ANIMATE_PHOTO="animate_photo"`; `VramTier(str, Enum)` со значениями `SAFE="safe"`, `WARNING="warning"`, `HIDDEN="hidden"`, `UNKNOWN="unknown"`; `Template` (dataclass: `name: str, title: str, category: str, tags: list[str], models: list[str], vram_bytes: int | None, size_bytes: int | None, description: str = ""`); `DeviceInfo` (dataclass: `available_vram_bytes: int, device_type: str, source: str`).

- [ ] **Step 1: Написать падающий тест**

`tests/test_models.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тест падает**

```bash
pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.models'`

- [ ] **Step 3: Реализовать `models.py`**

`src/comfygen/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class GenerationType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    ANIMATE_PHOTO = "animate_photo"


class VramTier(str, Enum):
    SAFE = "safe"
    WARNING = "warning"
    HIDDEN = "hidden"
    UNKNOWN = "unknown"


@dataclass
class Template:
    name: str
    title: str
    category: str
    tags: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    vram_bytes: int | None = None
    size_bytes: int | None = None
    description: str = ""


@dataclass
class DeviceInfo:
    available_vram_bytes: int
    device_type: str
    source: str
```

- [ ] **Step 4: Прогнать тесты**

```bash
pytest tests/test_models.py -v
```

Expected: PASS (4 passed)

- [ ] **Step 5: Коммит**

```bash
git add src/comfygen/models.py tests/test_models.py
git commit -m "feat: модели данных Template, DeviceInfo, GenerationType, VramTier"
```

---

## Task 3: Каталог шаблонов (загрузка, кеш, фильтрация)

**Files:**
- Create: `src/comfygen/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `comfygen.models.Template`, `comfygen.models.GenerationType` (Task 2).
- Produces: `INDEX_URL: str`, `TEMPLATE_FILE_URL_TEMPLATE: str`, `fetch_remote_index(client: httpx.Client) -> list[dict]`, `fetch_remote_template(client: httpx.Client, name: str) -> dict`, `load_cached_index(cache_path: Path, ttl_seconds: int) -> list[dict] | None`, `save_cache(cache_path: Path, raw_index: list[dict]) -> None`, `get_index(client: httpx.Client, cache_path: Path, ttl_seconds: int, force_refresh: bool = False) -> list[dict]`, `parse_templates(raw_index: list[dict]) -> list[Template]`, `filter_by_generation_type(templates: list[Template], gen_type: GenerationType) -> list[Template]`.

- [ ] **Step 1: Написать падающие тесты на кеширование и HTTP-загрузку**

`tests/test_catalog.py` (часть 1 из 2, добавить в файл):

```python
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
```

- [ ] **Step 2: Написать падающие тесты на парсинг и фильтрацию**

Добавить в конец `tests/test_catalog.py`:

```python
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
```

- [ ] **Step 3: Убедиться, что все тесты падают**

```bash
pytest tests/test_catalog.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.catalog'`

- [ ] **Step 4: Реализовать `catalog.py`**

`src/comfygen/catalog.py`:

```python
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
    return json.loads(cache_path.read_text(encoding="utf-8"))


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
                )
            )
    return templates


def filter_by_generation_type(templates: list[Template], gen_type: GenerationType) -> list[Template]:
    if gen_type == GenerationType.PHOTO:
        return [t for t in templates if t.category == "image" and "Text to Image" in t.tags]
    if gen_type == GenerationType.AUDIO:
        return [t for t in templates if t.category == "audio"]
    if gen_type == GenerationType.VIDEO:
        return [t for t in templates if t.category == "video" and "Image to Video" not in t.tags]
    if gen_type == GenerationType.ANIMATE_PHOTO:
        return [t for t in templates if t.category == "video" and "Image to Video" in t.tags]
    raise ValueError(f"Неизвестный тип генерации: {gen_type}")
```

- [ ] **Step 5: Прогнать тесты**

```bash
pytest tests/test_catalog.py -v
```

Expected: PASS (10 passed)

- [ ] **Step 6: Коммит**

```bash
git add src/comfygen/catalog.py tests/test_catalog.py
git commit -m "feat: загрузка, кеширование и фильтрация каталога шаблонов Comfy"
```

---

## Task 4: Фильтрация по VRAM (тиры Safe/Warning/Hidden/Unknown)

**Files:**
- Create: `src/comfygen/vram_filter.py`
- Test: `tests/test_vram_filter.py`

**Interfaces:**
- Consumes: `comfygen.models.Template`, `comfygen.models.DeviceInfo`, `comfygen.models.VramTier` (Task 2).
- Produces: `classify_template(template: Template, device: DeviceInfo, safe_factor: float, warning_factor: float) -> VramTier`, `classify_templates(templates: list[Template], device: DeviceInfo, safe_factor: float, warning_factor: float) -> dict[VramTier, list[Template]]`.

- [ ] **Step 1: Написать падающий тест**

`tests/test_vram_filter.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тест падает**

```bash
pytest tests/test_vram_filter.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.vram_filter'`

- [ ] **Step 3: Реализовать `vram_filter.py`**

`src/comfygen/vram_filter.py`:

```python
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
```

- [ ] **Step 4: Прогнать тесты**

```bash
pytest tests/test_vram_filter.py -v
```

Expected: PASS (5 passed)

- [ ] **Step 5: Коммит**

```bash
git add src/comfygen/vram_filter.py tests/test_vram_filter.py
git commit -m "feat: трёхуровневая фильтрация шаблонов по VRAM"
```

---

## Task 5: Определение характеристик устройства через ОС

**Files:**
- Create: `src/comfygen/device_detect.py`
- Test: `tests/test_device_detect.py`

**Interfaces:**
- Consumes: `comfygen.models.DeviceInfo` (Task 2), `comfygen.config.DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR` (Task 1).
- Produces: `class UnsupportedPlatformError(RuntimeError)`, `class DeviceDetectionError(RuntimeError)`, `detect_via_os(apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR) -> DeviceInfo`, `_query_nvidia_smi_vram() -> int | None` (внутренняя, но тестируется напрямую).

Эта задача покрывает только детекцию через ОС. Детекция через API ComfyUI и гибридный режим добавляются в Task 6, после того как появится `ComfyClient`.

- [ ] **Step 1: Написать падающие тесты**

`tests/test_device_detect.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
pytest tests/test_device_detect.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.device_detect'`

- [ ] **Step 3: Реализовать детекцию через ОС**

`src/comfygen/device_detect.py`:

```python
from __future__ import annotations

import platform
import subprocess

import psutil

from comfygen.config import DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR
from comfygen.models import DeviceInfo


class UnsupportedPlatformError(RuntimeError):
    pass


class DeviceDetectionError(RuntimeError):
    pass


def detect_via_os(
    apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR,
) -> DeviceInfo:
    system = platform.system()
    if system == "Darwin":
        return _detect_macos(apple_unified_memory_factor)
    if system == "Windows":
        return _detect_windows()
    raise UnsupportedPlatformError(f"Платформа {system} не поддерживается для детекции через ОС")


def _detect_macos(apple_unified_memory_factor: float) -> DeviceInfo:
    if platform.machine() == "arm64":
        total_ram = psutil.virtual_memory().total
        return DeviceInfo(
            available_vram_bytes=int(total_ram * apple_unified_memory_factor),
            device_type="mps",
            source="os",
        )
    return DeviceInfo(available_vram_bytes=0, device_type="cpu", source="os")


def _detect_windows() -> DeviceInfo:
    vram = _query_nvidia_smi_vram()
    if vram is not None:
        return DeviceInfo(available_vram_bytes=vram, device_type="cuda", source="os")
    return DeviceInfo(available_vram_bytes=0, device_type="cpu", source="os")


def _query_nvidia_smi_vram() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    first_line = result.stdout.strip().splitlines()[0]
    return int(first_line.strip()) * 1024 * 1024
```

- [ ] **Step 4: Прогнать тесты**

```bash
pytest tests/test_device_detect.py -v
```

Expected: PASS (7 passed)

- [ ] **Step 5: Коммит**

```bash
git add src/comfygen/device_detect.py tests/test_device_detect.py
git commit -m "feat: определение VRAM/GPU устройства через ОС (macOS/Windows)"
```

---

## Task 6: HTTP-клиент ComfyUI + детекция через API и гибридный режим

**Files:**
- Create: `src/comfygen/comfy_client.py`
- Modify: `src/comfygen/device_detect.py`
- Modify: `tests/test_device_detect.py`
- Test: `tests/test_comfy_client.py`

**Interfaces:**
- Consumes: `httpx` (внешняя библиотека).
- Produces: `class ComfyClient` с методами `__init__(self, base_url: str, http_client: httpx.Client | None = None)`, `health_check(self, timeout: float = 2.0) -> bool`, `system_stats(self) -> dict`, `upload_image(self, file_path: Path) -> str`, `save_workflow(self, filename: str, workflow: dict) -> None`. Добавляет в `device_detect.py`: `class SupportsSystemStats(Protocol)`, `detect_via_api(client: SupportsSystemStats) -> DeviceInfo`, `detect_hybrid(client: SupportsSystemStats, apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR) -> DeviceInfo`.

**Важное техническое допущение**, требующее проверки на реальном ComfyUI (см. Step 7): путь для сохранения workflow — `POST {base_url}/userdata/workflows%2F{filename}?overwrite=true` (aiohttp-роут ComfyUI `/userdata/{file}` ожидает URL-encoded слэши в имени пути). Если при ручной проверке на реальном сервере окажется иначе (например, префикс `/api/userdata/...` в более новых версиях ComfyUI) — обновить константу `SAVE_WORKFLOW_PATH_TEMPLATE` в `comfy_client.py`.

- [ ] **Step 1: Написать падающие тесты для `ComfyClient`**

`tests/test_comfy_client.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
pytest tests/test_comfy_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.comfy_client'`

- [ ] **Step 3: Реализовать `comfy_client.py`**

`src/comfygen/comfy_client.py`:

```python
from __future__ import annotations

from pathlib import Path

import httpx

SAVE_WORKFLOW_PATH_TEMPLATE = "{base_url}/userdata/workflows%2F{filename}?overwrite=true"


class ComfyClient:
    def __init__(self, base_url: str, http_client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.Client()

    def health_check(self, timeout: float = 2.0) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/system_stats", timeout=timeout)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def system_stats(self) -> dict:
        response = self._client.get(f"{self.base_url}/system_stats", timeout=10.0)
        response.raise_for_status()
        return response.json()

    def upload_image(self, file_path: Path) -> str:
        with file_path.open("rb") as f:
            response = self._client.post(
                f"{self.base_url}/upload/image",
                files={"image": (file_path.name, f, "application/octet-stream")},
                timeout=30.0,
            )
        response.raise_for_status()
        return response.json()["name"]

    def save_workflow(self, filename: str, workflow: dict) -> None:
        url = SAVE_WORKFLOW_PATH_TEMPLATE.format(base_url=self.base_url, filename=filename)
        response = self._client.post(url, json=workflow, timeout=15.0)
        response.raise_for_status()
```

- [ ] **Step 4: Прогнать тесты `ComfyClient`**

```bash
pytest tests/test_comfy_client.py -v
```

Expected: PASS (6 passed)

- [ ] **Step 5: Добавить падающие тесты для детекции через API и гибридного режима**

Добавить в конец `tests/test_device_detect.py`:

```python
from comfygen.device_detect import detect_hybrid, detect_via_api


class FakeComfyClient:
    def __init__(self, healthy: bool, stats: dict):
        self._healthy = healthy
        self._stats = stats

    def health_check(self, timeout: float = 2.0) -> bool:
        return self._healthy

    def system_stats(self) -> dict:
        return self._stats


def test_detect_via_api_parses_first_device():
    client = FakeComfyClient(healthy=True, stats={"devices": [{"type": "cuda", "vram_total": 25757220864}]})
    info = detect_via_api(client)
    assert info.device_type == "cuda"
    assert info.available_vram_bytes == 25757220864
    assert info.source == "api"


def test_detect_hybrid_uses_api_when_healthy():
    client = FakeComfyClient(healthy=True, stats={"devices": [{"type": "mps", "vram_total": 17179869184}]})
    info = detect_hybrid(client)
    assert info.source == "hybrid-api"
    assert info.available_vram_bytes == 17179869184


def test_detect_hybrid_falls_back_to_os_when_unhealthy(monkeypatch):
    monkeypatch.setattr("comfygen.device_detect.platform.system", lambda: "Darwin")
    monkeypatch.setattr("comfygen.device_detect.platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "comfygen.device_detect.psutil.virtual_memory",
        lambda: FakeVirtualMemory(total=16 * 1024**3),
    )
    client = FakeComfyClient(healthy=False, stats={})
    info = detect_hybrid(client, apple_unified_memory_factor=0.7)
    assert info.source == "hybrid-os"
```

- [ ] **Step 6: Дополнить `device_detect.py` детекцией через API и гибридным режимом**

Добавить в `src/comfygen/device_detect.py` (после импортов, перед `class UnsupportedPlatformError`):

```python
from typing import Protocol


class SupportsSystemStats(Protocol):
    def health_check(self, timeout: float = ...) -> bool: ...
    def system_stats(self) -> dict: ...
```

Добавить в конец `src/comfygen/device_detect.py`:

```python
def detect_via_api(client: SupportsSystemStats) -> DeviceInfo:
    stats = client.system_stats()
    devices = stats.get("devices") or []
    if not devices:
        raise DeviceDetectionError("ComfyUI /system_stats вернул пустой список устройств")
    device = devices[0]
    return DeviceInfo(
        available_vram_bytes=int(device.get("vram_total", 0)),
        device_type=device.get("type", "unknown"),
        source="api",
    )


def detect_hybrid(
    client: SupportsSystemStats,
    apple_unified_memory_factor: float = DEFAULT_APPLE_UNIFIED_MEMORY_FACTOR,
) -> DeviceInfo:
    if client.health_check():
        info = detect_via_api(client)
        return DeviceInfo(info.available_vram_bytes, info.device_type, source="hybrid-api")
    info = detect_via_os(apple_unified_memory_factor)
    return DeviceInfo(info.available_vram_bytes, info.device_type, source="hybrid-os")
```

- [ ] **Step 7: Прогнать все тесты детекции**

```bash
pytest tests/test_device_detect.py -v
```

Expected: PASS (10 passed)

- [ ] **Step 8: Ручная проверка `/userdata` на реальном ComfyUI (если доступен)**

Если под рукой есть запущенный ComfyUI: выполнить `curl -X POST "http://127.0.0.1:8188/userdata/workflows%2Ftest_comfygen.json?overwrite=true" -H "Content-Type: application/json" -d '{"nodes":[]}'` и убедиться, что файл появился в `user/default/workflows/test_comfygen.json` и в панели Workflows интерфейса. При расхождении — поправить `SAVE_WORKFLOW_PATH_TEMPLATE` в `comfy_client.py`, перезапустить тесты Step 4/7. Если ComfyUI недоступен на этапе реализации — задокументировать это как открытый риск и перепроверить перед первым релизом.

- [ ] **Step 9: Коммит**

```bash
git add src/comfygen/comfy_client.py src/comfygen/device_detect.py tests/test_comfy_client.py tests/test_device_detect.py
git commit -m "feat: HTTP-клиент ComfyUI, детекция устройства через API и гибридный режим"
```

---

## Task 7: Редактирование workflow (промпт, параметры, входное изображение)

**Files:**
- Create: `src/comfygen/workflow_editor.py`
- Test: `tests/test_workflow_editor.py`

**Interfaces:**
- Consumes: ничего специфичного для проекта (работает с сырыми `dict`, полученными из `catalog.fetch_remote_template`).
- Produces: `iter_all_nodes(workflow: dict) -> Iterator[dict]`, `load_workflow_file(path: Path) -> dict`, `set_positive_prompt(workflow: dict, text: str) -> bool`, `set_negative_prompt(workflow: dict, text: str) -> bool`, `set_resolution(workflow: dict, width: int, height: int) -> bool`, `set_seed(workflow: dict, seed: int) -> bool`, `set_steps(workflow: dict, steps: int) -> bool`, `set_image_input(workflow: dict, filename: str) -> bool`.

**Ключевая особенность**, обнаруженная при исследовании реальных шаблонов Comfy (`image_z_image_turbo.json`): многие workflow «subgraph»-ированы — верхнеуровневый `workflow["nodes"]` содержит лишь узел-обёртку с UUID-типом, а реальные узлы (`CLIPTextEncode`, `KSampler`, `EmptySD3LatentImage` и т.д.) лежат в `workflow["definitions"]["subgraphs"][*]["nodes"]`. Все функции ниже обязаны находить узлы в обоих местах через `iter_all_nodes`.

- [ ] **Step 1: Написать падающие тесты**

`tests/test_workflow_editor.py`:

```python
import copy

from comfygen.workflow_editor import (
    iter_all_nodes,
    set_image_input,
    set_negative_prompt,
    set_positive_prompt,
    set_resolution,
    set_seed,
    set_steps,
)

FLAT_WORKFLOW = {
    "nodes": [
        {"id": 1, "type": "CLIPTextEncode", "widgets_values": ["old positive"]},
        {"id": 2, "type": "CLIPTextEncode", "widgets_values": ["old negative"]},
        {"id": 3, "type": "EmptyLatentImage", "widgets_values": [512, 512, 1]},
        {"id": 4, "type": "KSampler", "widgets_values": [0, "randomize", 20, 7, "euler", "normal", 1]},
        {"id": 5, "type": "LoadImage", "widgets_values": ["example.png", "image"]},
    ],
    "definitions": {"subgraphs": []},
}

SUBGRAPHED_WORKFLOW = {
    "nodes": [
        {"id": 9, "type": "SaveImage", "widgets_values": ["output"]},
        {"id": 57, "type": "f2fdebf6-uuid", "widgets_values": []},
    ],
    "definitions": {
        "subgraphs": [
            {
                "id": "f2fdebf6-uuid",
                "nodes": [
                    {"id": 27, "type": "CLIPTextEncode", "widgets_values": ["old positive"]},
                    {"id": 13, "type": "EmptySD3LatentImage", "widgets_values": [1024, 1024, 1]},
                    {
                        "id": 3,
                        "type": "KSampler",
                        "widgets_values": [0, "randomize", 8, 1, "res_multistep", "simple", 1],
                    },
                ],
            }
        ]
    },
}


def test_iter_all_nodes_flat():
    names = [n["type"] for n in iter_all_nodes(FLAT_WORKFLOW)]
    assert names == ["CLIPTextEncode", "CLIPTextEncode", "EmptyLatentImage", "KSampler", "LoadImage"]


def test_iter_all_nodes_includes_subgraph_nodes():
    names = [n["type"] for n in iter_all_nodes(SUBGRAPHED_WORKFLOW)]
    assert "CLIPTextEncode" in names
    assert "KSampler" in names


def test_set_positive_prompt_patches_first_text_encode_node():
    workflow = copy.deepcopy(FLAT_WORKFLOW)
    assert set_positive_prompt(workflow, "a cat astronaut") is True
    assert workflow["nodes"][0]["widgets_values"][0] == "a cat astronaut"
    assert workflow["nodes"][1]["widgets_values"][0] == "old negative"


def test_set_negative_prompt_patches_second_text_encode_node():
    workflow = copy.deepcopy(FLAT_WORKFLOW)
    assert set_negative_prompt(workflow, "blurry, low quality") is True
    assert workflow["nodes"][1]["widgets_values"][0] == "blurry, low quality"


def test_set_negative_prompt_returns_false_when_no_second_node():
    workflow = copy.deepcopy(SUBGRAPHED_WORKFLOW)
    assert set_negative_prompt(workflow, "blurry") is False


def test_set_positive_prompt_works_inside_subgraph():
    workflow = copy.deepcopy(SUBGRAPHED_WORKFLOW)
    assert set_positive_prompt(workflow, "a cat astronaut") is True
    subgraph_node = workflow["definitions"]["subgraphs"][0]["nodes"][0]
    assert subgraph_node["widgets_values"][0] == "a cat astronaut"


def test_set_resolution_patches_latent_node():
    workflow = copy.deepcopy(FLAT_WORKFLOW)
    assert set_resolution(workflow, 768, 1024) is True
    assert workflow["nodes"][2]["widgets_values"][:2] == [768, 1024]


def test_set_resolution_works_inside_subgraph():
    workflow = copy.deepcopy(SUBGRAPHED_WORKFLOW)
    assert set_resolution(workflow, 768, 1024) is True
    subgraph_node = workflow["definitions"]["subgraphs"][0]["nodes"][1]
    assert subgraph_node["widgets_values"][:2] == [768, 1024]


def test_set_resolution_returns_false_when_no_latent_node():
    workflow = {"nodes": [], "definitions": {"subgraphs": []}}
    assert set_resolution(workflow, 768, 1024) is False


def test_set_seed_patches_ksampler_first_widget():
    workflow = copy.deepcopy(FLAT_WORKFLOW)
    assert set_seed(workflow, 12345) is True
    assert workflow["nodes"][3]["widgets_values"][0] == 12345


def test_set_steps_patches_ksampler_third_widget():
    workflow = copy.deepcopy(FLAT_WORKFLOW)
    assert set_steps(workflow, 30) is True
    assert workflow["nodes"][3]["widgets_values"][2] == 30


def test_set_image_input_patches_load_image_node():
    workflow = copy.deepcopy(FLAT_WORKFLOW)
    assert set_image_input(workflow, "uploaded_photo.png") is True
    assert workflow["nodes"][4]["widgets_values"][0] == "uploaded_photo.png"


def test_set_image_input_returns_false_when_no_load_image_node():
    workflow = {"nodes": [], "definitions": {"subgraphs": []}}
    assert set_image_input(workflow, "uploaded_photo.png") is False
```

- [ ] **Step 2: Убедиться, что тесты падают**

```bash
pytest tests/test_workflow_editor.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'comfygen.workflow_editor'`

- [ ] **Step 3: Реализовать `workflow_editor.py`**

`src/comfygen/workflow_editor.py`:

```python
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

POSITIVE_PROMPT_NODE_TYPES = {
    "CLIPTextEncode",
    "CLIPTextEncodeSDXL",
    "T5TextEncode",
    "CLIPTextEncodeFlux",
    "CLIPTextEncodeHunyuanDiT",
}
LATENT_SIZE_NODE_TYPES = {
    "EmptyLatentImage",
    "EmptySD3LatentImage",
    "EmptyHunyuanLatentVideo",
    "EmptyLatentVideo",
}
SAMPLER_NODE_TYPES = {"KSampler"}
IMAGE_INPUT_NODE_TYPES = {"LoadImage"}


def load_workflow_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_all_nodes(workflow: dict) -> Iterator[dict]:
    yield from workflow.get("nodes", [])
    for subgraph in workflow.get("definitions", {}).get("subgraphs", []):
        yield from subgraph.get("nodes", [])


def _find_nodes_by_type(workflow: dict, node_types: set[str]) -> list[dict]:
    return [n for n in iter_all_nodes(workflow) if n.get("type") in node_types]


def set_positive_prompt(workflow: dict, text: str) -> bool:
    nodes = _find_nodes_by_type(workflow, POSITIVE_PROMPT_NODE_TYPES)
    if not nodes:
        return False
    nodes[0]["widgets_values"][0] = text
    return True


def set_negative_prompt(workflow: dict, text: str) -> bool:
    nodes = _find_nodes_by_type(workflow, POSITIVE_PROMPT_NODE_TYPES)
    if len(nodes) < 2:
        return False
    nodes[1]["widgets_values"][0] = text
    return True


def set_resolution(workflow: dict, width: int, height: int) -> bool:
    nodes = _find_nodes_by_type(workflow, LATENT_SIZE_NODE_TYPES)
    if not nodes:
        return False
    widgets_values = nodes[0].get("widgets_values") or []
    if len(widgets_values) < 2:
        return False
    widgets_values[0] = width
    widgets_values[1] = height
    return True


def set_seed(workflow: dict, seed: int) -> bool:
    nodes = _find_nodes_by_type(workflow, SAMPLER_NODE_TYPES)
    if not nodes:
        return False
    widgets_values = nodes[0].get("widgets_values") or []
    if len(widgets_values) < 1:
        return False
    widgets_values[0] = seed
    return True


def set_steps(workflow: dict, steps: int) -> bool:
    nodes = _find_nodes_by_type(workflow, SAMPLER_NODE_TYPES)
    if not nodes:
        return False
    widgets_values = nodes[0].get("widgets_values") or []
    if len(widgets_values) < 3:
        return False
    widgets_values[2] = steps
    return True


def set_image_input(workflow: dict, filename: str) -> bool:
    nodes = _find_nodes_by_type(workflow, IMAGE_INPUT_NODE_TYPES)
    if not nodes:
        return False
    widgets_values = nodes[0].get("widgets_values") or []
    if not widgets_values:
        return False
    widgets_values[0] = filename
    return True
```

- [ ] **Step 4: Прогнать тесты**

```bash
pytest tests/test_workflow_editor.py -v
```

Expected: PASS (12 passed)

- [ ] **Step 5: Коммит**

```bash
git add src/comfygen/workflow_editor.py tests/test_workflow_editor.py
git commit -m "feat: редактирование узлов workflow (промпт, параметры, входное изображение)"
```

---

## Task 8: Интерактивный CLI-слой (ui.py)

**Files:**
- Create: `src/comfygen/ui.py`

**Interfaces:**
- Consumes: `comfygen.models.{GenerationType, VramTier, Template, DeviceInfo}` (Task 2).
- Produces: `choose_generation_type() -> GenerationType`, `choose_device_detection_method() -> str` (возвращает `"api" | "os" | "hybrid"`), `render_templates_table(tiers: dict[VramTier, list[Template]], include_unknown: bool = False) -> None`, `ask_show_unknown_tier(count: int) -> bool`, `choose_template(tiers: dict[VramTier, list[Template]], include_unknown: bool = False) -> Template | None`, `ask_prompt() -> str`, `ask_extra_params_wanted() -> bool`, `ask_negative_prompt() -> str | None`, `ask_resolution() -> tuple[int, int] | None`, `ask_seed_and_steps() -> tuple[int | None, int | None]`, `ask_image_input_choice() -> Path | None`.

Этот модуль — тонкая обёртка над `rich`/`questionary`, юнит-тестами не покрывается (интерактивный ввод), проверяется вручную в Task 10.

- [ ] **Step 1: Реализовать `ui.py`**

`src/comfygen/ui.py`:

```python
from __future__ import annotations

from pathlib import Path

import questionary
from rich.console import Console
from rich.table import Table

from comfygen.models import DeviceInfo, GenerationType, Template, VramTier

console = Console()

GENERATION_TYPE_LABELS = {
    GenerationType.PHOTO: "Фото (текст → изображение)",
    GenerationType.VIDEO: "Видео (текст/изображение → видео)",
    GenerationType.AUDIO: "Аудио (текст → звук/музыка)",
    GenerationType.ANIMATE_PHOTO: "Оживление фото (изображение → короткое видео)",
}

TIER_LABELS = {
    VramTier.SAFE: "✅ Уверенно потянет",
    VramTier.WARNING: "⚠️ На грани, может быть медленно или зависнуть",
    VramTier.UNKNOWN: "❓ Требования к VRAM неизвестны — на свой риск",
}


def choose_generation_type() -> GenerationType:
    choice = questionary.select(
        "Что хотите сгенерировать?",
        choices=[
            questionary.Choice(title=label, value=gen_type)
            for gen_type, label in GENERATION_TYPE_LABELS.items()
        ],
    ).ask()
    if choice is None:
        raise KeyboardInterrupt
    return choice


def choose_device_detection_method() -> str:
    choice = questionary.select(
        "Как определить характеристики устройства?",
        choices=[
            questionary.Choice(title="Через API запущенного ComfyUI (точно)", value="api"),
            questionary.Choice(title="Через ОС напрямую (без запущенного ComfyUI)", value="os"),
            questionary.Choice(title="Гибрид: API, а если Comfy не запущен — через ОС", value="hybrid"),
        ],
    ).ask()
    if choice is None:
        raise KeyboardInterrupt
    return choice


def render_templates_table(tiers: dict[VramTier, list[Template]], include_unknown: bool = False) -> None:
    table = Table(title="Подходящие модели/шаблоны")
    table.add_column("№")
    table.add_column("Название")
    table.add_column("Статус")
    table.add_column("VRAM")
    row_index = 1
    shown_tiers = (VramTier.SAFE, VramTier.WARNING, VramTier.UNKNOWN) if include_unknown else (VramTier.SAFE, VramTier.WARNING)
    for tier in shown_tiers:
        for template in tiers.get(tier, []):
            vram_gb = f"{template.vram_bytes / 1024**3:.1f} GB" if template.vram_bytes else "—"
            table.add_row(str(row_index), template.title, TIER_LABELS[tier], vram_gb)
            row_index += 1
    console.print(table)


def ask_show_unknown_tier(count: int) -> bool:
    if count == 0:
        return False
    return bool(
        questionary.confirm(
            f"Есть ещё {count} шаблон(ов) с неизвестными требованиями к VRAM. Показать их тоже?",
            default=False,
        ).ask()
    )


def choose_template(tiers: dict[VramTier, list[Template]], include_unknown: bool = False) -> Template | None:
    candidates = tiers.get(VramTier.SAFE, []) + tiers.get(VramTier.WARNING, [])
    if include_unknown:
        candidates += tiers.get(VramTier.UNKNOWN, [])
    if not candidates:
        console.print("[red]Ни один шаблон не подходит под характеристики устройства.[/red]")
        return None
    choice = questionary.select(
        "Выберите модель/шаблон",
        choices=[questionary.Choice(title=t.title, value=t) for t in candidates],
    ).ask()
    return choice


def ask_prompt() -> str:
    return questionary.text("Введите промпт для генерации:").ask() or ""


def ask_extra_params_wanted() -> bool:
    return bool(questionary.confirm("Настроить дополнительные параметры (negative prompt, разрешение, seed, шаги)?", default=False).ask())


def ask_negative_prompt() -> str | None:
    value = questionary.text("Negative prompt (оставьте пустым, чтобы пропустить):").ask()
    return value or None


def ask_resolution() -> tuple[int, int] | None:
    if not questionary.confirm("Задать разрешение вручную?", default=False).ask():
        return None
    width = int(questionary.text("Ширина:", default="1024").ask())
    height = int(questionary.text("Высота:", default="1024").ask())
    return width, height


def ask_seed_and_steps() -> tuple[int | None, int | None]:
    seed = None
    steps = None
    if questionary.confirm("Задать seed вручную?", default=False).ask():
        seed = int(questionary.text("Seed:", default="0").ask())
    if questionary.confirm("Задать количество шагов вручную?", default=False).ask():
        steps = int(questionary.text("Шаги:", default="20").ask())
    return seed, steps


def ask_image_input_choice() -> Path | None:
    choice = questionary.select(
        "Входное изображение для видео/оживления фото:",
        choices=[
            questionary.Choice(title="Указать путь к файлу сейчас", value="now"),
            questionary.Choice(title="Пропустить — выбрать позже прямо в ComfyUI", value="later"),
        ],
    ).ask()
    if choice != "now":
        return None
    path_str = questionary.path("Путь к изображению:").ask()
    return Path(path_str) if path_str else None
```

- [ ] **Step 2: Проверить, что модуль импортируется без ошибок**

```bash
python -c "import comfygen.ui"
```

Expected: без вывода/ошибок (успешный импорт)

- [ ] **Step 3: Коммит**

```bash
git add src/comfygen/ui.py
git commit -m "feat: интерактивный CLI-слой на rich/questionary"
```

---

## Task 9: Точка входа и оркестрация (`__main__.py`)

**Files:**
- Create: `src/comfygen/__main__.py`

**Interfaces:**
- Consumes: все модули из Task 1–8.
- Produces: `main() -> None` — точка входа, зарегистрированная в `pyproject.toml` как `comfygen`.

- [ ] **Step 1: Реализовать `__main__.py`**

`src/comfygen/__main__.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from rich.console import Console

from comfygen.catalog import fetch_remote_template, filter_by_generation_type, get_index, parse_templates
from comfygen.comfy_client import ComfyClient
from comfygen.config import CACHE_PATH, load_config
from comfygen.device_detect import DeviceDetectionError, UnsupportedPlatformError, detect_hybrid, detect_via_api, detect_via_os
from comfygen.models import DeviceInfo, VramTier
from comfygen.vram_filter import classify_templates
from comfygen.workflow_editor import (
    set_image_input,
    set_negative_prompt,
    set_positive_prompt,
    set_resolution,
    set_seed,
    set_steps,
)
from comfygen import ui

console = Console()


def _detect_device(method: str, client: ComfyClient, config) -> DeviceInfo:
    if method == "api":
        return detect_via_api(client)
    if method == "os":
        return detect_via_os(config.apple_unified_memory_factor)
    return detect_hybrid(client, config.apple_unified_memory_factor)


def run(force_refresh: bool = False) -> None:
    config = load_config()
    client = ComfyClient(config.comfy_base_url)

    gen_type = ui.choose_generation_type()
    method = ui.choose_device_detection_method()

    try:
        device = _detect_device(method, client, config)
    except (DeviceDetectionError, UnsupportedPlatformError) as exc:
        console.print(f"[red]Не удалось определить характеристики устройства: {exc}[/red]")
        return
    except httpx.HTTPError as exc:
        console.print(
            f"[red]ComfyUI не отвечает на {config.comfy_base_url}: {exc}. "
            "Запустите ComfyUI или выберите другой способ детекции.[/red]"
        )
        return

    console.print(f"Обнаружено устройство: {device.device_type}, VRAM ≈ {device.available_vram_bytes / 1024**3:.1f} GB (источник: {device.source})")

    with httpx.Client() as http_client:
        try:
            raw_index = get_index(http_client, CACHE_PATH, config.cache_ttl_seconds, force_refresh=force_refresh)
        except httpx.HTTPError as exc:
            console.print(
                f"[red]Не удалось загрузить каталог моделей с GitHub: {exc}. "
                "Проверьте подключение к интернету и повторите.[/red]"
            )
            return

        templates = parse_templates(raw_index)
        candidates = filter_by_generation_type(templates, gen_type)
        tiers = classify_templates(candidates, device, config.vram_safe_factor, config.vram_warning_factor)

        ui.render_templates_table(tiers)
        unknown_count = len(tiers.get(VramTier.UNKNOWN, []))
        include_unknown = ui.ask_show_unknown_tier(unknown_count)
        if include_unknown:
            ui.render_templates_table(tiers, include_unknown=True)
        template = ui.choose_template(tiers, include_unknown=include_unknown)
        if template is None:
            return

        try:
            workflow = fetch_remote_template(http_client, template.name)
        except httpx.HTTPError as exc:
            console.print(f"[red]Не удалось загрузить файл шаблона {template.name}: {exc}[/red]")
            return

    prompt_text = ui.ask_prompt()
    set_positive_prompt(workflow, prompt_text)

    if ui.ask_extra_params_wanted():
        negative = ui.ask_negative_prompt()
        if negative:
            set_negative_prompt(workflow, negative)
        resolution = ui.ask_resolution()
        if resolution:
            set_resolution(workflow, *resolution)
        seed, steps = ui.ask_seed_and_steps()
        if seed is not None:
            set_seed(workflow, seed)
        if steps is not None:
            set_steps(workflow, steps)

    if gen_type.value in ("video", "animate_photo"):
        image_path = ui.ask_image_input_choice()
        if image_path is not None:
            if not client.health_check():
                console.print("[red]ComfyUI не запущен — не могу загрузить изображение. Запустите ComfyUI и повторите.[/red]")
                return
            uploaded_name = client.upload_image(image_path)
            set_image_input(workflow, uploaded_name)

    if not client.health_check():
        console.print(f"[red]ComfyUI не запущен на {config.comfy_base_url} — запустите его, чтобы сохранить workflow.[/red]")
        return

    output_filename = f"comfygen_{template.name}.json"
    client.save_workflow(output_filename, workflow)
    console.print(f"[green]Готово! Workflow сохранён в ComfyUI как \"{output_filename}\" — откройте его на вкладке Workflows и нажмите Queue.[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(prog="comfygen", description="CLI-помощник для генерации в ComfyUI")
    parser.add_argument("--refresh", action="store_true", help="Принудительно обновить кеш каталога шаблонов Comfy")
    args = parser.parse_args()
    try:
        run(force_refresh=args.refresh)
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано пользователем.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Проверить, что модуль импортируется и `--help` работает**

```bash
python -m comfygen --help
```

Expected: вывод справки argparse без трейсбека (`usage: comfygen ...`)

- [ ] **Step 3: Ручной smoke-test с запущенным ComfyUI (если доступен)**

Запустить ComfyUI локально, затем `python -m comfygen`, пройти по одному сценарию для типа "Фото": выбрать способ детекции "через API", убедиться, что таблица шаблонов отрисовалась, выбрать любой шаблон, ввести промпт, отказаться от доп. параметров, дождаться сообщения об успешном сохранении, открыть ComfyUI в браузере и убедиться, что workflow появился на вкладке Workflows с подставленным промптом.

- [ ] **Step 4: Коммит**

```bash
git add src/comfygen/__main__.py
git commit -m "feat: оркестрация всего сценария и точка входа comfygen"
```

---

## Task 10: Bootstrap-лаунчеры run.sh / run.bat

**Files:**
- Create: `run.sh`
- Create: `run.bat`

**Interfaces:**
- Consumes: `pyproject.toml` (Task 1), консольный скрипт `comfygen` (Task 9).
- Produces: исполняемые лаунчеры, не имеющие Python-интерфейса (запускаются пользователем напрямую).

- [ ] **Step 1: Создать `run.sh`**

`run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d "$VENV_DIR" ]; then
    echo "Создаю виртуальное окружение в $VENV_DIR..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if [ ! -f "$VENV_DIR/.deps_installed" ] || [ "$SCRIPT_DIR/pyproject.toml" -nt "$VENV_DIR/.deps_installed" ]; then
    echo "Устанавливаю зависимости..."
    pip install --quiet --upgrade pip
    pip install --quiet -e "$SCRIPT_DIR"
    touch "$VENV_DIR/.deps_installed"
fi

exec comfygen "$@"
```

- [ ] **Step 2: Сделать `run.sh` исполняемым**

```bash
chmod +x run.sh
```

- [ ] **Step 3: Создать `run.bat`**

`run.bat`:

```bat
@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"

if not exist "%VENV_DIR%" (
    echo Создаю виртуальное окружение в %VENV_DIR%...
    python -m venv "%VENV_DIR%"
)

call "%VENV_DIR%\Scripts\activate.bat"

if not exist "%VENV_DIR%\.deps_installed" (
    echo Устанавливаю зависимости...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -e "%SCRIPT_DIR%."
    type nul > "%VENV_DIR%\.deps_installed"
)

comfygen %*
```

- [ ] **Step 4: Проверить `run.sh` на macOS/Linux**

```bash
rm -rf .venv  # чистый прогон, имитирует первый запуск
./run.sh --help
```

Expected: скрипт создаёт `.venv`, ставит зависимости, выводит справку `comfygen --help` без ошибок. Повторный запуск `./run.sh --help` не должен переустанавливать зависимости (файл `.venv/.deps_installed` уже свежий).

- [ ] **Step 5: Задокументировать проверку на Windows**

Windows-проверка `run.bat --help` по тому же сценарию (чистая `.venv`, создание окружения, установка зависимостей, справка без ошибок) выполняется вручную на Windows-машине при первом релизе — в текущем окружении (macOS) выполнить её невозможно.

- [ ] **Step 6: Коммит**

```bash
git add run.sh run.bat
git commit -m "feat: self-bootstrapping launcher-скрипты для macOS и Windows"
```

---

## Task 11: Финальный сквозной smoke-test и минимальный README

**Files:**
- Create: `README.md`

**Interfaces:**
- Нет программных интерфейсов — финальная проверка и минимальная документация для пользователя, объявленная в `pyproject.toml` (`readme = "README.md"`).

- [ ] **Step 1: Прогнать весь набор тестов проекта**

```bash
pytest -v
```

Expected: все тесты из Task 1–7 проходят (config, models, catalog, vram_filter, device_detect, comfy_client, workflow_editor).

- [ ] **Step 2: Создать минимальный `README.md`**

`README.md`:

```markdown
# ComfyGen

CLI-помощник для генерации в ComfyUI: выбираете тип генерации (фото, видео, аудио, оживление фото), программа сама проверяет характеристики вашего устройства и предлагает только те модели, которые оно потянет, запрашивает промпт и сохраняет готовый workflow прямо в ComfyUI.

## Запуск

Требуется Python 3.10+ и запущенный локально [ComfyUI](https://github.com/comfyanonymous/ComfyUI).

macOS/Linux:

​```bash
./run.sh
​```

Windows:

​```bat
run.bat
​```

Первый запуск сам создаст виртуальное окружение и установит зависимости — вручную ничего ставить не нужно.

Флаг `--refresh` принудительно обновляет локальный кеш каталога моделей Comfy:

​```bash
./run.sh --refresh
​```
```

- [ ] **Step 3: Сквозной ручной smoke-test на macOS с реальным ComfyUI**

Пройти по одному полному сценарию для каждого из 4 типов генерации (Фото, Видео, Аудио, Оживление фото) через `./run.sh`, с запущенным локально ComfyUI: для каждого — выбрать тип, детекцию через "гибрид", выбрать шаблон из Safe-тира, ввести промпт, для видео/оживления фото — оставить выбор изображения "на потом", убедиться, что workflow появляется в ComfyUI на вкладке Workflows и открывается без ошибок.

- [ ] **Step 4: Сквозной ручной smoke-test на Windows**

Тот же сценарий (минимум для типа "Фото") на Windows-машине с NVIDIA GPU через `run.bat`, с запущенным локально ComfyUI.

- [ ] **Step 5: Коммит**

```bash
git add README.md
git commit -m "docs: README с инструкцией по запуску ComfyGen"
```
