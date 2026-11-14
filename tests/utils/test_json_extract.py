from src.utils.json_extract import extract_json_object


def test_object_inside_markdown_fence():
    assert extract_json_object('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_brace_inside_a_string_does_not_end_the_object():
    assert extract_json_object('x {"a": "}"} y') == '{"a": "}"}'


def test_no_object_returns_none():
    assert extract_json_object("no json here") is None
