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
