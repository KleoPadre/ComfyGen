import copy

from comfygen.workflow_editor import (
    iter_all_nodes,
    set_image_input,
    set_negative_prompt,
    set_negative_prompt_via_schema,
    set_positive_prompt,
    set_positive_prompt_via_schema,
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


def test_set_positive_prompt_returns_false_when_widgets_values_too_short():
    workflow = {
        "nodes": [{"id": 1, "type": "CLIPTextEncode", "widgets_values": []}],
        "definitions": {"subgraphs": []},
    }
    assert set_positive_prompt(workflow, "hello") is False


def test_set_negative_prompt_returns_false_when_widgets_values_too_short():
    workflow = {
        "nodes": [
            {"id": 1, "type": "CLIPTextEncode", "widgets_values": ["positive"]},
            {"id": 2, "type": "CLIPTextEncode", "widgets_values": []},
        ],
        "definitions": {"subgraphs": []},
    }
    assert set_negative_prompt(workflow, "blurry") is False


# Структура, воспроизводящая реальный баг: у sdxl_simple_example (base+refiner)
# порядок узлов в файле НЕ совпадает с их ролью в графе связей — node 7 идёт в
# файле раньше node 6, но по факту именно node 6 подключён как "positive" к
# сэмплеру 10, а node 7 — как "negative". Наивный подход "первый найденный
# CLIPTextEncode = positive" подставлял бы промпт пользователя в негатив.
SDXL_BASE_REFINER_WORKFLOW = {
    "nodes": [
        {"id": 7, "type": "CLIPTextEncode", "widgets_values": ["original base text (node 7)"]},
        {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["original base text (node 6)"]},
        {"id": 16, "type": "CLIPTextEncode", "widgets_values": ["text, watermark"]},
        {"id": 15, "type": "CLIPTextEncode", "widgets_values": ["original refiner text (node 15)"]},
        {
            "id": 10,
            "type": "KSamplerAdvanced",
            "inputs": [
                {"name": "model", "type": "MODEL", "link": 10},
                {"name": "positive", "type": "CONDITIONING", "link": 11},
                {"name": "negative", "type": "CONDITIONING", "link": 12},
            ],
            "widgets_values": [],
        },
        {
            "id": 11,
            "type": "KSamplerAdvanced",
            "inputs": [
                {"name": "model", "type": "MODEL", "link": 14},
                {"name": "positive", "type": "CONDITIONING", "link": 23},
                {"name": "negative", "type": "CONDITIONING", "link": 24},
            ],
            "widgets_values": [],
        },
    ],
    "links": [
        [11, 6, 0, 10, 1, "CONDITIONING"],
        [12, 7, 0, 10, 2, "CONDITIONING"],
        [23, 15, 0, 11, 1, "CONDITIONING"],
        [24, 16, 0, 11, 2, "CONDITIONING"],
    ],
    "definitions": {"subgraphs": []},
}


def test_set_positive_prompt_uses_link_graph_not_file_order():
    workflow = copy.deepcopy(SDXL_BASE_REFINER_WORKFLOW)
    assert set_positive_prompt(workflow, "new prompt") is True
    by_id = {n["id"]: n for n in workflow["nodes"]}
    # node 6 подключён как positive у сэмплера 10 -> должен получить промпт
    assert by_id[6]["widgets_values"][0] == "new prompt"
    # node 7 подключён как negative -> не должен быть тронут set_positive_prompt
    assert by_id[7]["widgets_values"][0] == "original base text (node 7)"


def test_set_positive_prompt_patches_all_stages_of_multi_sampler_pipeline():
    workflow = copy.deepcopy(SDXL_BASE_REFINER_WORKFLOW)
    assert set_positive_prompt(workflow, "new prompt") is True
    by_id = {n["id"]: n for n in workflow["nodes"]}
    # и base (node 6), и refiner (node 15) positive-узлы должны обновиться
    assert by_id[6]["widgets_values"][0] == "new prompt"
    assert by_id[15]["widgets_values"][0] == "new prompt"


def test_set_negative_prompt_uses_link_graph_not_file_order():
    workflow = copy.deepcopy(SDXL_BASE_REFINER_WORKFLOW)
    assert set_negative_prompt(workflow, "bad hands") is True
    by_id = {n["id"]: n for n in workflow["nodes"]}
    assert by_id[7]["widgets_values"][0] == "bad hands"
    assert by_id[16]["widgets_values"][0] == "bad hands"
    # positive-узлы не должны быть тронуты set_negative_prompt
    assert by_id[6]["widgets_values"][0] == "original base text (node 6)"
    assert by_id[15]["widgets_values"][0] == "original refiner text (node 15)"


# Реальный баг №2: SDXL Turbo использует SamplerCustom (не KSampler/
# KSamplerAdvanced) — консюмер CONDITIONING может быть узлом ЛЮБОГО типа,
# нельзя ограничиваться списком известных сэмплеров.
SAMPLER_CUSTOM_WORKFLOW = {
    "nodes": [
        {"id": 7, "type": "CLIPTextEncode", "widgets_values": ["original negative (node 7)"]},
        {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["original positive (node 6)"]},
        {
            "id": 13,
            "type": "SamplerCustom",
            "inputs": [
                {"name": "model", "type": "MODEL", "link": 41},
                {"name": "positive", "type": "CONDITIONING", "link": 19},
                {"name": "negative", "type": "CONDITIONING", "link": 20},
            ],
            "widgets_values": [],
        },
    ],
    "links": [
        [19, 6, 0, 13, 1, "CONDITIONING"],
        [20, 7, 0, 13, 2, "CONDITIONING"],
    ],
    "definitions": {"subgraphs": []},
}


def test_set_positive_prompt_resolves_arbitrary_sampler_node_type():
    workflow = copy.deepcopy(SAMPLER_CUSTOM_WORKFLOW)
    assert set_positive_prompt(workflow, "new prompt") is True
    by_id = {n["id"]: n for n in workflow["nodes"]}
    assert by_id[6]["widgets_values"][0] == "new prompt"
    assert by_id[7]["widgets_values"][0] == "original negative (node 7)"


def test_set_negative_prompt_resolves_arbitrary_sampler_node_type():
    workflow = copy.deepcopy(SAMPLER_CUSTOM_WORKFLOW)
    assert set_negative_prompt(workflow, "bad hands") is True
    by_id = {n["id"]: n for n in workflow["nodes"]}
    assert by_id[7]["widgets_values"][0] == "bad hands"
    assert by_id[6]["widgets_values"][0] == "original positive (node 6)"


WAN_TEXT_TO_IMAGE_API_INFO = {
    "input": {
        "required": {
            "model": ["COMBO", {"options": ["wan2.5-t2i-preview"]}],
            "prompt": ["STRING", {"default": "", "multiline": True}],
        },
        "optional": {
            "negative_prompt": ["STRING", {"default": "", "multiline": True}],
            "width": ["INT", {"default": 1024}],
        },
    },
    "input_order": {
        "required": ["model", "prompt"],
        "optional": ["negative_prompt", "width"],
    },
}

WAN_API_NODE_WORKFLOW = {
    "nodes": [
        {
            "id": 12,
            "type": "WanTextToImageApi",
            "inputs": [],
            "widgets_values": ["wan2.5-t2i-preview", "old prompt", "", 1024],
        },
    ],
    "definitions": {"subgraphs": []},
}


class FakeObjectInfoClient:
    """Заглушка client.object_info(node_type) для тестов без реальной сети."""

    def __init__(self, info_by_type: dict[str, dict]):
        self._info_by_type = info_by_type

    def object_info(self, node_type: str) -> dict:
        if node_type not in self._info_by_type:
            raise KeyError(node_type)
        return self._info_by_type[node_type]


def test_set_positive_prompt_via_schema_patches_named_widget():
    workflow = copy.deepcopy(WAN_API_NODE_WORKFLOW)
    client = FakeObjectInfoClient({"WanTextToImageApi": WAN_TEXT_TO_IMAGE_API_INFO})
    assert set_positive_prompt_via_schema(workflow, "new prompt", client) is True
    assert workflow["nodes"][0]["widgets_values"][1] == "new prompt"
    assert workflow["nodes"][0]["widgets_values"][0] == "wan2.5-t2i-preview"


def test_set_negative_prompt_via_schema_patches_named_widget():
    workflow = copy.deepcopy(WAN_API_NODE_WORKFLOW)
    client = FakeObjectInfoClient({"WanTextToImageApi": WAN_TEXT_TO_IMAGE_API_INFO})
    assert set_negative_prompt_via_schema(workflow, "blurry", client) is True
    assert workflow["nodes"][0]["widgets_values"][2] == "blurry"


def test_set_positive_prompt_via_schema_returns_false_when_object_info_unavailable():
    workflow = copy.deepcopy(WAN_API_NODE_WORKFLOW)
    client = FakeObjectInfoClient({})
    assert set_positive_prompt_via_schema(workflow, "new prompt", client) is False
    assert workflow["nodes"][0]["widgets_values"][1] == "old prompt"


def test_set_positive_prompt_via_schema_works_inside_subgraph():
    workflow = {
        "nodes": [{"id": 57, "type": "uuid-subgraph", "widgets_values": []}],
        "definitions": {
            "subgraphs": [
                {
                    "id": "uuid-subgraph",
                    "nodes": [copy.deepcopy(WAN_API_NODE_WORKFLOW["nodes"][0])],
                }
            ]
        },
    }
    client = FakeObjectInfoClient({"WanTextToImageApi": WAN_TEXT_TO_IMAGE_API_INFO})
    assert set_positive_prompt_via_schema(workflow, "new prompt", client) is True
    subgraph_node = workflow["definitions"]["subgraphs"][0]["nodes"][0]
    assert subgraph_node["widgets_values"][1] == "new prompt"
