from __future__ import annotations

WIDGET_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN", "COMBO"}
CONTROL_AFTER_GENERATE = "__control_after_generate__"

PROMPT_NAME_ALIASES = {"prompt", "text", "text_g", "positive_prompt", "positive"}
NEGATIVE_NAME_ALIASES = {"negative_prompt", "negative_text", "negative"}


def _input_defs(object_info: dict) -> dict:
    input_defs: dict = {}
    input_defs.update(object_info.get("input", {}).get("required", {}))
    input_defs.update(object_info.get("input", {}).get("optional", {}))
    return input_defs


def ordered_widget_names(object_info: dict, node: dict) -> list[str]:
    """Имена widget-виджетов узла в том же порядке, в котором ComfyUI сериализует
    их значения в ``widgets_values``.

    Учитывает две особенности фронтенда ComfyUI:
    - входы, подключённые связью (есть в ``node["inputs"]`` с непустым ``link``),
      не имеют собственного виджета и в ``widgets_values`` отсутствуют;
    - у INT/FLOAT-входов с ``control_after_generate: true`` (typically seed)
      фронтенд добавляет сразу после них ещё один служебный виджет
      (combo "fixed/increment/decrement/randomize") — отмечается сентинелом
      ``__control_after_generate__``.
    """
    linked_names = {inp.get("name") for inp in node.get("inputs", []) if inp.get("link") is not None}
    input_defs = _input_defs(object_info)
    input_order = object_info.get("input_order", {})
    names = list(input_order.get("required", [])) + list(input_order.get("optional", []))

    result: list[str] = []
    for name in names:
        if name in linked_names:
            continue
        spec = input_defs.get(name)
        if not spec or not isinstance(spec, list):
            continue
        type_name = spec[0]
        meta = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        if not isinstance(type_name, str) or type_name not in WIDGET_TYPES:
            continue
        result.append(name)
        if meta.get("control_after_generate"):
            result.append(CONTROL_AFTER_GENERATE)
    return result


def find_widget_index(
    object_info: dict,
    node: dict,
    name_aliases: set[str],
    require_multiline: bool = False,
) -> int | None:
    """Найти позицию в ``widgets_values`` узла по одному из имён входа схемы."""
    input_defs = _input_defs(object_info)
    for index, name in enumerate(ordered_widget_names(object_info, node)):
        if name not in name_aliases:
            continue
        if require_multiline:
            spec = input_defs.get(name)
            meta = spec[1] if spec and len(spec) > 1 and isinstance(spec[1], dict) else {}
            if not meta.get("multiline"):
                continue
        return index
    return None
