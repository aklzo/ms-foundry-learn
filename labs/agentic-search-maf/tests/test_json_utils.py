import pytest

from agentic_search_maf.errors import LlmResponseError
from agentic_search_maf.json_utils import extract_json


def test_parses_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_parses_json_inside_code_fence():
    text = 'Here you go:\n```json\n{"queries": ["rust async"]}\n```\nDone.'
    assert extract_json(text)["queries"] == ["rust async"]


def test_parses_array_with_surrounding_prose():
    assert extract_json("results: [1, 2, 3] as requested") == [1, 2, 3]


def test_handles_braces_inside_strings():
    value = extract_json('{"note": "uses { and } inside"} trailing')
    assert value["note"] == "uses { and } inside"


def test_rejects_text_without_json():
    with pytest.raises(LlmResponseError):
        extract_json("no structured data here")
