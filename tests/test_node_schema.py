from comfygen.node_schema import (
    NEGATIVE_NAME_ALIASES,
    PROMPT_NAME_ALIASES,
    find_widget_index,
    ordered_widget_names,
)

WAN_TEXT_TO_IMAGE_API_INFO = {
    "input": {
        "required": {
            "model": ["COMBO", {"options": ["wan2.5-t2i-preview"]}],
            "prompt": ["STRING", {"default": "", "multiline": True}],
        },
        "optional": {
            "negative_prompt": ["STRING", {"default": "", "multiline": True}],
            "width": ["INT", {"default": 1024}],
            "height": ["INT", {"default": 1024}],
            "seed": ["INT", {"default": 0, "control_after_generate": True}],
            "prompt_extend": ["BOOLEAN", {"default": True}],
            "watermark": ["BOOLEAN", {"default": False}],
        },
    },
    "input_order": {
        "required": ["model", "prompt"],
        "optional": ["negative_prompt", "width", "height", "seed", "prompt_extend", "watermark"],
    },
}

WAN_NODE = {
    "id": 12,
    "type": "WanTextToImageApi",
    "inputs": [],
    "widgets_values": [
        "wan2.5-t2i-preview",
        "old prompt",
        "",
        1024,
        1024,
        6926862,
        "randomize",
        True,
        False,
    ],
}


def test_ordered_widget_names_inserts_control_after_generate_after_seed():
    names = ordered_widget_names(WAN_TEXT_TO_IMAGE_API_INFO, WAN_NODE)
    assert names == [
        "model",
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "seed",
        "__control_after_generate__",
        "prompt_extend",
        "watermark",
    ]


def test_ordered_widget_names_matches_widgets_values_length():
    names = ordered_widget_names(WAN_TEXT_TO_IMAGE_API_INFO, WAN_NODE)
    assert len(names) == len(WAN_NODE["widgets_values"])


def test_ordered_widget_names_skips_linked_inputs():
    node_with_link = {
        "id": 12,
        "type": "WanTextToImageApi",
        "inputs": [{"name": "model", "type": "COMBO", "link": 7}],
        "widgets_values": ["old prompt", "", 1024, 1024, 6926862, "randomize", True, False],
    }
    names = ordered_widget_names(WAN_TEXT_TO_IMAGE_API_INFO, node_with_link)
    assert "model" not in names
    assert names[0] == "prompt"


def test_find_widget_index_locates_prompt():
    index = find_widget_index(WAN_TEXT_TO_IMAGE_API_INFO, WAN_NODE, PROMPT_NAME_ALIASES, require_multiline=True)
    assert index == 1
    assert WAN_NODE["widgets_values"][index] == "old prompt"


def test_find_widget_index_locates_negative_prompt():
    index = find_widget_index(WAN_TEXT_TO_IMAGE_API_INFO, WAN_NODE, NEGATIVE_NAME_ALIASES, require_multiline=True)
    assert index == 2
    assert WAN_NODE["widgets_values"][index] == ""


def test_find_widget_index_returns_none_when_no_match():
    index = find_widget_index(WAN_TEXT_TO_IMAGE_API_INFO, WAN_NODE, {"nonexistent_alias"})
    assert index is None


def test_find_widget_index_require_multiline_excludes_non_multiline_string():
    info = {
        "input": {
            "required": {"prompt": ["STRING", {"multiline": False}]},
            "optional": {},
        },
        "input_order": {"required": ["prompt"], "optional": []},
    }
    node = {"id": 1, "type": "X", "inputs": [], "widgets_values": ["short text"]}
    assert find_widget_index(info, node, PROMPT_NAME_ALIASES, require_multiline=True) is None
    assert find_widget_index(info, node, PROMPT_NAME_ALIASES, require_multiline=False) == 0
