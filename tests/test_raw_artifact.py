"""Raw artifact digest tests."""

from __future__ import annotations

from vana_integrity.raw_artifact import compute_content_digest, format_input_ref, parse_input_ref


def test_same_content_same_hash() -> None:
    content = '{"fixture":"synthetic_observation_001","version":1}'
    assert compute_content_digest(content) == compute_content_digest(content)


def test_modified_content_different_hash() -> None:
    original = '{"fixture":"synthetic_observation_001","version":1}'
    modified = '{"fixture":"synthetic_observation_001","version":2}'
    assert compute_content_digest(original) != compute_content_digest(modified)


def test_input_ref_format_and_parse() -> None:
    content = "raw-bytes"
    ref = "fixtures/example.json"
    input_ref = format_input_ref(content, ref)
    assert input_ref.startswith("sha256:")
    assert "|ref:fixtures/example.json" in input_ref

    parsed = parse_input_ref(input_ref)
    assert parsed["ref"] == ref
    assert parsed["sha256"] == compute_content_digest(content)
