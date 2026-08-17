"""Raw artifact digest and DB table persistence tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_raw_artifact_table_persisted(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    response = client.post("/ingest/observations", json=synthetic_payload)
    assert response.status_code == 201

    row = db_conn.execute("SELECT * FROM raw_artifact WHERE observation_id = 'OBSERVATION-001'").fetchone()
    assert row is not None
    assert row["hash_algorithm"] == "sha256"
    assert row["content_hash"].startswith("sha256:")

