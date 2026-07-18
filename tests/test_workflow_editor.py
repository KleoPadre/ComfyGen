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
