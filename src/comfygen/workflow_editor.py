from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from comfygen import node_schema

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

# Типы узлов-потребителей CONDITIONING (сэмплеры), чьи именованные входы
# "positive"/"negative" однозначно определяют роль подключённого к ним
# текстового узла — используется ТОЛЬКО для разрешения роли по графу связей
# (см. _resolve_conditioning_sources), не для set_seed/set_steps: у разных
# типов сэмплеров разный порядок виджетов, здесь это не нужно.
CONDITIONING_CONSUMER_NODE_TYPES = {"KSampler", "KSamplerAdvanced"}


def load_workflow_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_all_nodes(workflow: dict) -> Iterator[dict]:
    yield from workflow.get("nodes", [])
    for subgraph in workflow.get("definitions", {}).get("subgraphs", []):
        yield from subgraph.get("nodes", [])


def _iter_scopes(workflow: dict) -> Iterator[tuple[list[dict], list]]:
    """(список узлов, список связей) для каждой независимой области видимости:
    верхний уровень workflow и каждый subgraph — связи не пересекают границы
    области видимости, поэтому разрешать их нужно раздельно."""
    yield workflow.get("nodes", []), workflow.get("links", [])
    for subgraph in workflow.get("definitions", {}).get("subgraphs", []):
        yield subgraph.get("nodes", []), subgraph.get("links", [])


def _build_link_origin_map(links: list) -> dict[int, int]:
    """link_id -> id узла-источника. Поддерживает оба формата, встречающихся
    в workflow ComfyUI: старый список ``[link_id, origin_id, origin_slot,
    target_id, target_slot, type]`` (верхний уровень) и словарь
    ``{"id":.., "origin_id":.., ...}`` (внутри subgraph)."""
    origin_by_link: dict[int, int] = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 2:
            link_id, origin_id = link[0], link[1]
        elif isinstance(link, dict):
            link_id, origin_id = link.get("id"), link.get("origin_id")
        else:
            continue
        if link_id is not None and origin_id is not None:
            origin_by_link[link_id] = origin_id
    return origin_by_link


def _resolve_conditioning_sources(workflow: dict, input_name: str) -> list[dict]:
    """Найти узлы, реально подключённые как ``positive``/``negative`` к
    сэмплерам — по графу связей, а не по порядку узлов в файле. Порядок
    узлов в JSON никак не гарантирует, что "первый найденный текстовый
    узел" — это positive: у многоступенчатых пайплайнов (например
    base+refiner у SDXL) узлов больше двух, и их порядок в файле может не
    совпадать с их ролью в графе."""
    resolved: list[dict] = []
    seen_ids: set[int] = set()
    for nodes, links in _iter_scopes(workflow):
        nodes_by_id = {n.get("id"): n for n in nodes}
        link_origin = _build_link_origin_map(links)
        for node in nodes:
            if node.get("type") not in CONDITIONING_CONSUMER_NODE_TYPES:
                continue
            for inp in node.get("inputs", []):
                if inp.get("name") != input_name or inp.get("type") != "CONDITIONING":
                    continue
                link_id = inp.get("link")
                if link_id is None:
                    continue
                origin_node = nodes_by_id.get(link_origin.get(link_id))
                if origin_node is None or origin_node.get("type") not in POSITIVE_PROMPT_NODE_TYPES:
                    continue
                if id(origin_node) in seen_ids:
                    continue
                seen_ids.add(id(origin_node))
                resolved.append(origin_node)
    return resolved


def _find_nodes_by_type(workflow: dict, node_types: set[str]) -> list[dict]:
    return [n for n in iter_all_nodes(workflow) if n.get("type") in node_types]


def _set_text_by_role(workflow: dict, text: str, role: str, fallback_index: int) -> bool:
    linked_nodes = _resolve_conditioning_sources(workflow, role)
    applied = False
    for node in linked_nodes:
        widgets_values = node.get("widgets_values") or []
        if len(widgets_values) < 1:
            continue
        widgets_values[0] = text
        applied = True
    if applied:
        return True

    # Запасной путь для workflow без явных input-связей у сэмплера (например,
    # узел изолирован или используется нестандартный тип сэмплера) —
    # прежняя эвристика "первый/второй найденный текстовый узел".
    nodes = _find_nodes_by_type(workflow, POSITIVE_PROMPT_NODE_TYPES)
    if len(nodes) <= fallback_index:
        return False
    widgets_values = nodes[fallback_index].get("widgets_values") or []
    if len(widgets_values) < 1:
        return False
    widgets_values[0] = text
    return True


def set_positive_prompt(workflow: dict, text: str) -> bool:
    return _set_text_by_role(workflow, text, "positive", fallback_index=0)


def set_negative_prompt(workflow: dict, text: str) -> bool:
    return _set_text_by_role(workflow, text, "negative", fallback_index=1)


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


class SupportsObjectInfo(Protocol):
    def object_info(self, node_type: str) -> dict: ...


def _set_text_via_schema(workflow: dict, text: str, client: SupportsObjectInfo, aliases: set[str]) -> bool:
    """Найти узел, чья ЖИВАЯ схема (/object_info) объявляет multiline-текстовый вход
    с одним из имён-алиасов, и подставить туда текст.

    В отличие от `set_positive_prompt`/`set_negative_prompt` (фиксированный список
    типов узлов, индекс 0/1), этот путь работает для ЛЮБОГО типа узла — включая
    API-ноды (WanTextToImageApi и т.п.), где промпт не первый/второй виджет и тип
    узла не входит и не может заранее входить в статический список.
    """
    for node in iter_all_nodes(workflow):
        node_type = node.get("type")
        if not isinstance(node_type, str):
            continue
        try:
            info = client.object_info(node_type)
        except Exception:
            continue
        if not info:
            continue
        index = node_schema.find_widget_index(info, node, aliases, require_multiline=True)
        if index is None:
            continue
        widgets_values = node.get("widgets_values") or []
        if index >= len(widgets_values):
            continue
        widgets_values[index] = text
        return True
    return False


def set_positive_prompt_via_schema(workflow: dict, text: str, client: SupportsObjectInfo) -> bool:
    return _set_text_via_schema(workflow, text, client, node_schema.PROMPT_NAME_ALIASES)


def set_negative_prompt_via_schema(workflow: dict, text: str, client: SupportsObjectInfo) -> bool:
    return _set_text_via_schema(workflow, text, client, node_schema.NEGATIVE_NAME_ALIASES)
