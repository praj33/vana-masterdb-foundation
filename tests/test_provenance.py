"""Provenance chain persistence tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_provenance_chain_created(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    response = client.post("/ingest/observations", json=synthetic_payload)
    assert response.status_code == 201
    observation_id = response.json()["observation_id"]

    source = db_conn.execute(
        "SELECT source_id FROM source WHERE source_id = ?",
        (synthetic_payload["source"]["source_id"],),
    ).fetchone()
    assert source is not None

    dataset = db_conn.execute(
        "SELECT dataset_id FROM dataset WHERE dataset_id = ?",
        (synthetic_payload["dataset"]["dataset_id"],),
    ).fetchone()
    assert dataset is not None

    observation = db_conn.execute(
        "SELECT observation_id FROM observation WHERE observation_id = ?",
        (observation_id,),
    ).fetchone()
    assert observation is not None

    measurements = db_conn.execute(
        "SELECT measurement_id FROM measurement WHERE observation_id = ?",
        (observation_id,),
    ).fetchall()
    assert len(measurements) == len(synthetic_payload["measurements"])

    runs = db_conn.execute(
        "SELECT run_id, input_ref FROM processing_run WHERE dataset_id = ?",
        (synthetic_payload["dataset"]["dataset_id"],),
    ).fetchall()
    assert len(runs) >= 1
    assert runs[0]["input_ref"].startswith("sha256:")

    provenance_rows = db_conn.execute(
        """
        SELECT p.provenance_id
        FROM provenance p
        JOIN measurement m ON m.measurement_id = p.measurement_id
        WHERE m.observation_id = ?
        """,
        (observation_id,),
    ).fetchall()
    assert len(provenance_rows) == len(synthetic_payload["measurements"])


def test_provenance_preserved_after_retry(
    client: TestClient,
    db_conn,
    synthetic_payload: dict,
) -> None:
    headers = {"Idempotency-Key": "prov-retry-key"}
    first = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    before = db_conn.execute("SELECT COUNT(*) AS c FROM provenance").fetchone()["c"]

    second = client.post("/ingest/observations", json=synthetic_payload, headers=headers)
    after = db_conn.execute("SELECT COUNT(*) AS c FROM provenance").fetchone()["c"]

    assert first.status_code == 201
    assert second.status_code == 200
    assert before == after
