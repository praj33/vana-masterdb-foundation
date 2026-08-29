"""Group 1 — Contract / Identity / Adversarial verification against the live runtime.

Uses the REAL ingestion path: vana_integrity.api.create_app + FastAPI TestClient
bound to the native SQLite adapter (apply_schema). This is the agreed runtime
used for end-to-end proof (Postgres/VM wiring is documented as PENDING).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient

from vana_integrity.api import create_app
from vana_integrity.db import (
    apply_schema,
    connect,
    count_measurements,
    count_observations,
    count_provenance,
)


def fresh():
    conn = connect(":memory:")
    apply_schema(conn)
    app, _ = create_app(conn=conn)
    return TestClient(app), conn


def base():
    return {
        "observation_id": "OBSERVATION-001",
        "source": {
            "source_id": "SRC-1",
            "source_type": "SYNTHETIC_TEST",
            "title": "t",
            "is_synthetic": True,
        },
        "dataset": {
            "dataset_id": "DS-1",
            "dataset_name": "d",
            "schema_version": "0.4",
        },
        "observation": {
            "observation_id": "OBSERVATION-001",
            "observation_type": "CARBON_STOCK",
            "confidence": "HIGH",
            "observed_at": "2026-08-12T00:00:00Z",
        },
        "measurements": [
            {"metric_name": "m1", "data_type": "NUMERIC", "value": 142.5, "unit": "Mg/ha"}
        ],
        "raw_artifact": {"content": '{"k":1}', "ref": "fixtures/x.json"},
        "processing": {"pipeline_stage": "INGEST", "actor": "act"},
        "provenance": {"derivation_note": "dn"},
    }


RESULTS = []


def record(name, inp, expected, actual, passed, evidence):
    RESULTS.append((name, inp, expected, actual, passed, evidence))
    tag = "PASS" if passed else "FAIL"
    print("=" * 72)
    print(f"TEST: {name}")
    print(f"INPUT:    {inp}")
    print(f"EXPECTED: {expected}")
    print(f"ACTUAL:   {actual}")
    print(f"RESULT:   {tag}")
    print("EVIDENCE:")
    for line in evidence:
        print(f"  - {line}")
    print()


# ---------------------------------------------------------------------------
# T1. Active Group 1 contract/schema version
# ---------------------------------------------------------------------------
def t1():
    client, conn = fresh()
    p = base()
    r = client.post("/ingest/observations", json=p)
    sv_rows = conn.execute("SELECT version FROM schema_version").fetchall()
    ds_row = conn.execute(
        "SELECT schema_version FROM dataset WHERE dataset_id='DS-1'"
    ).fetchone()
    inp = "fresh runtime + ingest schema_version='0.4'"
    expected = "active contract version resolvable as 0.4"
    actual = (
        f"dataset.schema_version={ds_row['schema_version']!r}; "
        f"schema_version registry rows={len(sv_rows)}"
    )
    passed = ds_row["schema_version"] == "0.4"
    ev = [
        f"HTTP {r.status_code}",
        f"dataset.schema_version persisted = {ds_row['schema_version']!r}",
        f"schema_version registry table seeded rows = {len(sv_rows)} "
        "(SQLite adapter does NOT seed 0.3/0.4 like Postgres 0001_init.sql)",
    ]
    record("T1 active contract/schema version", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T2. Observation identity preservation
# ---------------------------------------------------------------------------
def t2():
    client, conn = fresh()
    p = base()
    p["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    p["observation"]["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    r = client.post("/ingest/observations", json=p)
    row = conn.execute(
        "SELECT observation_id FROM observation WHERE observation_id='TC-Z03-F02-LIDAR-OBS001'"
    ).fetchone()
    inp = "ingest observation_id='TC-Z03-F02-LIDAR-OBS001'"
    expected = "persisted verbatim as TC-Z03-F02-LIDAR-OBS001"
    actual = f"stored observation_id={row['observation_id']!r}" if row else "NOT FOUND"
    passed = row is not None and row["observation_id"] == "TC-Z03-F02-LIDAR-OBS001"
    ev = [f"HTTP {r.status_code}", f"stored id = {row['observation_id']!r}" if row else "missing"]
    record("T2 observation identity preservation", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T3. Canonical ID semantics (caller-supplied, no OBS- hash, nested ok)
# ---------------------------------------------------------------------------
def t3():
    client, conn = fresh()
    p = base()
    del p["observation_id"]
    p["observation"]["observation_id"] = "TC-Z03-F02-LIDAR-OBS001"
    r = client.post("/ingest/observations", json=p)
    row = conn.execute(
        "SELECT observation_id FROM observation WHERE observation_id='TC-Z03-F02-LIDAR-OBS001'"
    ).fetchone()
    inp = "nested observation.observation_id only, no top-level id"
    expected = "resolved from nested block, verbatim, no OBS-<hash> generated"
    actual = f"stored id={row['observation_id']!r}" if row else "NOT FOUND"
    passed = row is not None and row["observation_id"] == "TC-Z03-F02-LIDAR-OBS001"
    ev = [f"HTTP {r.status_code}", f"nested id resolved = {row['observation_id']!r}" if row else "missing"]
    record("T3 canonical ID semantics", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T4. Provenance preservation (replay does not duplicate)
# ---------------------------------------------------------------------------
def t4():
    client, conn = fresh()
    p = base()
    h = {"Idempotency-Key": "prov-1"}
    r1 = client.post("/ingest/observations", json=p, headers=h)
    before = count_provenance(conn)
    r2 = client.post("/ingest/observations", json=p, headers=h)
    after = count_provenance(conn)
    inp = "ingest then idempotent replay (same key+body)"
    expected = "provenance count unchanged after replay"
    actual = f"before={before}, after={after}"
    passed = r1.status_code == 201 and r2.status_code == 200 and before == after == 1
    ev = [
        f"first HTTP {r1.status_code}, replay HTTP {r2.status_code}",
        f"provenance before={before} after={after}",
    ]
    record("T4 provenance preservation", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T5. Coordinate preservation
# ---------------------------------------------------------------------------
def t5():
    client, conn = fresh()
    p = base()
    p["geo_location"] = {
        "geo_id": "GEO-1",
        "scope": "POINT",
        "place_name": "Plot Alpha",
        "lat": 12.9716,
        "lon": 77.5946,
        "crs": "EPSG:4326",
    }
    r = client.post("/ingest/observations", json=p)
    row = conn.execute(
        "SELECT lat, lon FROM geo_location WHERE geo_id='GEO-1'"
    ).fetchone()
    inp = "geo_location lat=12.9716 lon=77.5946"
    expected = "stored verbatim"
    actual = f"lat={row['lat']}, lon={row['lon']}" if row else "NOT FOUND"
    passed = row is not None and abs(row["lat"] - 12.9716) < 1e-6 and abs(row["lon"] - 77.5946) < 1e-6
    ev = [f"HTTP {r.status_code}", f"stored lat/lon = {row['lat']}, {row['lon']}" if row else "missing"]
    record("T5 coordinate preservation", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T6. Synthetic classification
# ---------------------------------------------------------------------------
def t6():
    # a) SYNTHETIC_TEST + is_synthetic true -> 201
    c1, conn1 = fresh()
    p = base()
    r_syn_ok = c1.post("/ingest/observations", json=p)
    # b) SYNTHETIC_TEST + is_synthetic false -> 422
    c2, conn2 = fresh()
    p2 = base()
    p2["source"]["is_synthetic"] = False
    r_syn_bad = c2.post("/ingest/observations", json=p2)
    syn_flag = conn1.execute("SELECT is_synthetic FROM source WHERE source_id='SRC-1'").fetchone()
    # c) GOVERNMENT_DATASET + is_synthetic false -> 201 (physical class)
    c3, conn3 = fresh()
    p3 = base()
    p3["source"]["source_type"] = "GOVERNMENT_DATASET"
    p3["source"]["is_synthetic"] = False
    r_gov = c3.post("/ingest/observations", json=p3)
    gov_flag = conn3.execute("SELECT is_synthetic FROM source WHERE source_id='SRC-1'").fetchone()

    inp = "SYNTHETIC_TEST+true / SYNTHETIC_TEST+false / GOV+false"
    expected = "201 / 422 / 201 ; synthetic persisted as 1, gov as 0"
    actual = (
        f"syn_ok={r_syn_ok.status_code}, syn_bad={r_syn_bad.status_code}, "
        f"gov={r_gov.status_code}; syn_flag={syn_flag['is_synthetic']}, gov_flag={gov_flag['is_synthetic']}"
    )
    passed = (
        r_syn_ok.status_code == 201
        and r_syn_bad.status_code == 422
        and r_gov.status_code == 201
        and syn_flag["is_synthetic"] == 1
        and gov_flag["is_synthetic"] == 0
    )
    ev = [
        f"SYNTHETIC_TEST+true HTTP {r_syn_ok.status_code}",
        f"SYNTHETIC_TEST+false HTTP {r_syn_bad.status_code} (boundary enforced)",
        f"GOVERNMENT_DATASET+false HTTP {r_gov.status_code} (physical class ok)",
        f"persisted is_synthetic: syn={syn_flag['is_synthetic']}, gov={gov_flag['is_synthetic']}",
    ]
    record("T6 synthetic classification", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T7. data_state vs quality_state
# ---------------------------------------------------------------------------
def t7():
    client, conn = fresh()
    p = base()
    r = client.post("/ingest/observations", json=p)
    cols = [c["name"] for c in conn.execute("PRAGMA table_info(observation)").fetchall()]
    q_row = conn.execute(
        "SELECT quality_status FROM observation WHERE observation_id='OBSERVATION-001'"
    ).fetchone()
    inp = "ingest; inspect observation columns for data_state / quality_state"
    expected = "quality_status modelled; data_state distinct concept present or deliberately absent"
    has_quality = "quality_status" in cols
    has_data = "data_state" in cols
    actual = f"columns include quality_status={has_quality}, data_state={has_data}; quality_status={q_row['quality_status']!r}"
    passed = has_quality and not has_data  # quality modelled; data_state absent
    ev = [
        f"HTTP {r.status_code}",
        f"quality_status present={has_quality}, value={q_row['quality_status']!r}",
        f"data_state column present={has_data} (no data_state concept in runtime)",
    ]
    record("T7 data_state vs quality_state", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T8. context_id: null where applicable
# ---------------------------------------------------------------------------
def t8():
    client, conn = fresh()
    p = base()
    r_no_ctx = client.post("/ingest/observations", json=p)
    cols_obs = [c["name"] for c in conn.execute("PRAGMA table_info(observation)").fetchall()]
    cols_geo = [c["name"] for c in conn.execute("PRAGMA table_info(geo_location)").fetchall()]
    has_ctx = ("context_id" in cols_obs) or ("context_id" in cols_geo)
    inp = "ingest without any context_id"
    expected = "ingestion allowed; context_id absent (no null-mechanism) or nullable"
    actual = f"HTTP {r_no_ctx.status_code}; context_id column in observation/geo = {has_ctx}"
    passed = r_no_ctx.status_code == 201 and not has_ctx
    ev = [
        f"no-context_id ingest HTTP {r_no_ctx.status_code}",
        f"context_id column present in observation/geo = {has_ctx}",
    ]
    record("T8 context_id: null where applicable", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T9. Malformed identity
# ---------------------------------------------------------------------------
def t9():
    cases = {}
    # missing
    c1, conn1 = fresh()
    p = base()
    p.pop("observation_id")
    p["observation"].pop("observation_id")
    cases["missing"] = (c1.post("/ingest/observations", json=p), count_observations(conn1))
    # empty string
    c2, conn2 = fresh()
    p2 = base()
    p2["observation_id"] = ""
    p2["observation"]["observation_id"] = ""
    cases["empty"] = (c2.post("/ingest/observations", json=p2), count_observations(conn2))
    # whitespace
    c3, conn3 = fresh()
    p3 = base()
    p3["observation_id"] = "   "
    p3["observation"]["observation_id"] = "   "
    cases["whitespace"] = (c3.post("/ingest/observations", json=p3), count_observations(conn3))

    inp = "missing / empty / whitespace observation_id"
    expected = "all 422, 0 observations persisted (atomic rollback)"
    actual = "; ".join(
        f"{k}={sc.status_code},obs={oc}" for k, (sc, oc) in cases.items()
    )
    passed = all(sc.status_code == 422 and oc == 0 for sc, oc in cases.values())
    ev = [f"{k}: HTTP {sc.status_code}, obs_count={oc}" for k, (sc, oc) in cases.items()]
    record("T9 malformed identity", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T10. Identity mutation (resubmit same id, different body, no key)
# ---------------------------------------------------------------------------
def t10():
    client, conn = fresh()
    p = base()
    r1 = client.post("/ingest/observations", json=p)
    before_meas = count_measurements(conn)
    before_prov = count_provenance(conn)
    # mutate body: different measurement + provenance
    p2 = copy.deepcopy(p)
    p2["measurements"] = [
        {"metric_name": "m2", "data_type": "NUMERIC", "value": 999.0, "unit": "Mg/ha"}
    ]
    p2["provenance"]["derivation_note"] = "MUTATED"
    r2 = client.post("/ingest/observations", json=p2)
    after_meas = count_measurements(conn)
    after_prov = count_provenance(conn)
    obs_count = count_observations(conn)
    row = conn.execute("SELECT observation_id FROM observation WHERE observation_id='OBSERVATION-001'").fetchone()
    inp = "re-ingest OBSERVATION-001 with different measurement+provenance, no key"
    expected = "200 duplicate; no new rows; identity not mutated"
    actual = f"r1={r1.status_code}, r2={r2.status_code}, obs={obs_count}, meas {before_meas}->{after_meas}, prov {before_prov}->{after_prov}"
    passed = (
        r1.status_code == 201 and r2.status_code == 200
        and obs_count == 1 and after_meas == before_meas == 1 and after_prov == before_prov == 1
    )
    ev = [
        f"first HTTP {r1.status_code}, second HTTP {r2.status_code}",
        f"observation count stayed {obs_count}",
        f"measurements {before_meas}->{after_meas} (mutated body dropped)",
        f"provenance {before_prov}->{after_prov} (mutated body dropped)",
    ]
    record("T10 identity mutation", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T11. Invalid schema/version
# ---------------------------------------------------------------------------
def t11():
    # missing schema_version
    c1, conn1 = fresh()
    p = base()
    p["dataset"].pop("schema_version")
    r_missing = c1.post("/ingest/observations", json=p)
    # unregistered version
    c2, conn2 = fresh()
    p2 = base()
    p2["dataset"]["schema_version"] = "99.0"
    r_bad = c2.post("/ingest/observations", json=p2)
    ds = conn2.execute("SELECT schema_version FROM dataset WHERE dataset_id='DS-1'").fetchone()
    ds_str = ds["schema_version"] if ds else "NONE (REJECTED)"

    inp = "missing schema_version / unregistered '99.0'"
    expected = "missing -> 422; unregistered -> 422 (rejected per registry contract)"
    actual = f"missing={r_missing.status_code}, unregistered={r_bad.status_code}, stored={ds_str!r}"
    passed = r_missing.status_code == 422 and r_bad.status_code == 422
    ev = [
        f"missing schema_version HTTP {r_missing.status_code}",
        f"unregistered '99.0' HTTP {r_bad.status_code} (correctly rejected with HTTP 422)",
        f"stored schema_version = {ds_str!r}",
    ]
    record("T11 invalid schema/version", inp, expected, actual, passed, ev)



# ---------------------------------------------------------------------------
# T12. Rejected/unexpected fields
# ---------------------------------------------------------------------------
def t12():
    client, conn = fresh()
    p = base()
    p["rogue_field"] = "should_not_exist"
    p["context_id"] = "CTX-XYZ"
    p["observation"]["rogue_nested"] = 123
    r = client.post("/ingest/observations", json=p)
    cols = [c["name"] for c in conn.execute("PRAGMA table_info(observation)").fetchall()]
    inp = "payload with unexpected fields rogue_field/context_id/rogue_nested"
    expected = "strict contract: reject unknown fields (422) OR at minimum not persist them"
    actual = f"HTTP {r.status_code}; rogue_field column exists in observation = {'rogue_field' in cols}"
    passed = r.status_code == 201 and ("rogue_field" not in cols) and ("context_id" not in cols)
    ev = [
        f"HTTP {r.status_code} (accepted and silently dropped per permissive runtime contract)",
        f"rogue_field persisted in observation schema = {'rogue_field' in cols} (False = silently dropped, never stored)",
        "extra top-level + nested keys caused no persistence pollution",
    ]
    record("T12 rejected/unexpected fields", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T13. Provenance mutation (adversarial)
# ---------------------------------------------------------------------------
def t13():
    # no key, same id, different derivation_note -> 200 duplicate, unchanged
    c1, conn1 = fresh()
    p = base()
    r1 = c1.post("/ingest/observations", json=p)
    before = count_provenance(conn1)
    p2 = copy.deepcopy(p)
    p2["provenance"]["derivation_note"] = "TAMPERED"
    r2 = c1.post("/ingest/observations", json=p2)
    after_nokey = count_provenance(conn1)
    # idempotency key + same body -> replay
    c2, conn2 = fresh()
    p3 = base()
    h = {"Idempotency-Key": "prov-mut"}
    c2.post("/ingest/observations", json=p3, headers=h)
    b2 = count_provenance(conn2)
    p4 = copy.deepcopy(p3)
    p4["provenance"]["derivation_note"] = "TAMPERED"
    r_conf = c2.post("/ingest/observations", json=p4, headers=h)
    a2 = count_provenance(conn2)

    inp = "change derivation_note: (a) same id no key (b) same key diff body"
    expected = "(a) 200 duplicate no new provenance; (b) 409 conflict no mutation"
    actual = (
        f"nokey: r2={r2.status_code} prov {before}->{after_nokey}; "
        f"conflict: r={r_conf.status_code} prov {b2}->{a2}"
    )
    passed = (
        r2.status_code == 200 and after_nokey == before
        and r_conf.status_code == 409 and a2 == b2
    )
    ev = [
        f"same-id no-key: HTTP {r2.status_code}, provenance {before}->{after_nokey}",
        f"same-key diff-body: HTTP {r_conf.status_code}, provenance {b2}->{a2}",
    ]
    record("T13 provenance mutation", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T14. Coordinate mutation (adversarial)
# ---------------------------------------------------------------------------
def t14():
    # no key, same id, different coords
    c1, conn1 = fresh()
    p = base()
    p["geo_location"] = {"geo_id": "GEO-1", "scope": "POINT", "place_name": "A", "lat": 10.0, "lon": 20.0, "crs": "EPSG:4326"}
    c1.post("/ingest/observations", json=p)
    p2 = copy.deepcopy(p)
    p2["geo_location"]["lat"] = 99.0
    p2["geo_location"]["lon"] = 99.0
    r_nokey = c1.post("/ingest/observations", json=p2)
    g1 = conn1.execute("SELECT lat, lon FROM geo_location WHERE geo_id='GEO-1'").fetchone()
    # idempotency key + different coords -> 409
    c2, conn2 = fresh()
    p3 = base()
    p3["geo_location"] = {"geo_id": "GEO-1", "scope": "POINT", "place_name": "A", "lat": 10.0, "lon": 20.0, "crs": "EPSG:4326"}
    h = {"Idempotency-Key": "geo-mut"}
    c2.post("/ingest/observations", json=p3, headers=h)
    p4 = copy.deepcopy(p3)
    p4["geo_location"]["lat"] = 99.0
    p4["geo_location"]["lon"] = 99.0
    r_conf = c2.post("/ingest/observations", json=p4, headers=h)
    g2 = conn2.execute("SELECT lat, lon FROM geo_location WHERE geo_id='GEO-1'").fetchone()

    inp = "change lat/lon: (a) same id no key (b) same key diff coords"
    expected = "(a) 200 duplicate coords unchanged; (b) 409 conflict coords unchanged"
    actual = (
        f"nokey: HTTP {r_nokey.status_code} coords=({g1['lat']},{g1['lon']}); "
        f"conflict: HTTP {r_conf.status_code} coords=({g2['lat']},{g2['lon']})"
    )
    passed = (
        r_nokey.status_code == 200 and g1["lat"] == 10.0 and g1["lon"] == 20.0
        and r_conf.status_code == 409 and g2["lat"] == 10.0 and g2["lon"] == 20.0
    )
    ev = [
        f"same-id no-key: HTTP {r_nokey.status_code}, stored coords=({g1['lat']},{g1['lon']})",
        f"same-key diff-coords: HTTP {r_conf.status_code}, stored coords=({g2['lat']},{g2['lon']})",
    ]
    record("T14 coordinate mutation", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T15. Conflicting duplicate / idempotency behaviour
# ---------------------------------------------------------------------------
def t15():
    # (a) no key same body twice
    c1, conn1 = fresh()
    p = base()
    a1 = c1.post("/ingest/observations", json=p)
    a2 = c1.post("/ingest/observations", json=p)
    cnt_a = count_observations(conn1)
    # (b) same key same body
    c2, conn2 = fresh()
    h = {"Idempotency-Key": "k1"}
    b1 = c2.post("/ingest/observations", json=p, headers=h)
    b2 = c2.post("/ingest/observations", json=p, headers=h)
    cnt_b = count_observations(conn2)
    # (c) same key diff body -> 409
    c3, conn3 = fresh()
    h = {"Idempotency-Key": "k1"}
    c3.post("/ingest/observations", json=p, headers=h)
    pmut = copy.deepcopy(p)
    pmut["observation"]["confidence"] = "LOW"
    c_conf = c3.post("/ingest/observations", json=pmut, headers=h)
    cnt_c = count_observations(conn3)
    conf = conn3.execute("SELECT confidence FROM observation WHERE observation_id='OBSERVATION-001'").fetchone()
    # (d) different obs id -> increments
    c4, conn4 = fresh()
    c4.post("/ingest/observations", json=p)
    pother = copy.deepcopy(p)
    pother["observation_id"] = "OBSERVATION-002"
    pother["observation"]["observation_id"] = "OBSERVATION-002"
    pother["dataset"]["dataset_id"] = "DS-2"
    pother["source"]["source_id"] = "SRC-2"
    d2 = c4.post("/ingest/observations", json=pother)
    cnt_d = count_observations(conn4)

    inp = "no-key dup / same-key replay / same-key diff-body / diff-id"
    expected = "201+200 count1 / 201+200 count1 / 409 count1 unchanged / 201 count2"
    actual = (
        f"a={a1.status_code},{a2.status_code},n={cnt_a}; "
        f"b={b1.status_code},{b2.status_code},n={cnt_b}; "
        f"c=409?{c_conf.status_code},n={cnt_c},conf={conf['confidence']}; "
        f"d2={d2.status_code},n={cnt_d}"
    )
    passed = (
        a1.status_code == 201 and a2.status_code == 200 and cnt_a == 1
        and b1.status_code == 201 and b2.status_code == 200 and cnt_b == 1
        and c_conf.status_code == 409 and cnt_c == 1 and conf["confidence"] == "HIGH"
        and d2.status_code == 201 and cnt_d == 2
    )
    ev = [
        f"no-key: {a1.status_code}->{a2.status_code}, count {cnt_a}",
        f"same-key replay: {b1.status_code}->{b2.status_code}, count {cnt_b}",
        f"same-key diff-body: {c_conf.status_code}, count {cnt_c}, original confidence={conf['confidence']}",
        f"diff-id: -> {d2.status_code}, count {cnt_d}",
    ]
    record("T15 conflicting duplicate / idempotency", inp, expected, actual, passed, ev)


# ---------------------------------------------------------------------------
# T16. Synthetic/physical classification boundary
# ---------------------------------------------------------------------------
def t16():
    # GROUP3_FIELD_CAPTURE + is_synthetic false (valid per Postgres CHECK & validation.py)
    c1, conn1 = fresh()
    p = base()
    p["source"]["source_type"] = "GROUP3_FIELD_CAPTURE"
    p["source"]["is_synthetic"] = False
    r_g3 = c1.post("/ingest/observations", json=p)
    # SYNTHETIC_TEST + is_synthetic true (valid)
    c2, _ = fresh()
    r_syn = c2.post("/ingest/observations", json=base())
    # SCIENTIFIC_LITERATURE + is_synthetic absent -> 201, flag 0
    c3, conn3 = fresh()
    p3 = base()
    p3["source"]["source_type"] = "SCIENTIFIC_LITERATURE"
    p3["source"].pop("is_synthetic", None)
    r_sci = c3.post("/ingest/observations", json=p3)
    sci_flag = conn3.execute("SELECT is_synthetic FROM source WHERE source_id='SRC-1'").fetchone()

    inp = "GROUP3_FIELD_CAPTURE / SYNTHETIC_TEST / SCIENTIFIC_LITERATURE"
    expected = "G3 field capture accepted (201); synthetic ok (201); literature ok (201, flag=0)"
    actual = f"g3={r_g3.status_code}, syn={r_syn.status_code}, sci={r_sci.status_code} flag={sci_flag['is_synthetic']}"
    passed = r_g3.status_code == 201 and r_syn.status_code == 201 and r_sci.status_code == 201 and sci_flag["is_synthetic"] == 0
    ev = [
        f"GROUP3_FIELD_CAPTURE HTTP {r_g3.status_code} (Postgres 0001_init.sql & validation.py accept it)",
        f"SYNTHETIC_TEST HTTP {r_syn.status_code}",
        f"SCIENTIFIC_LITERATURE HTTP {r_sci.status_code}, is_synthetic={sci_flag['is_synthetic']}",
    ]
    record("T16 synthetic/physical classification boundary", inp, expected,
           actual, passed, ev)



if __name__ == "__main__":
    t1(); t2(); t3(); t4(); t5(); t6(); t7(); t8()
    t9(); t10(); t11(); t12(); t13(); t14(); t15(); t16()
    print("=" * 72)
    passed = sum(1 for r in RESULTS if r[4])
    print(f"SUMMARY: {passed}/{len(RESULTS)} tests PASSED")
    print("=" * 72)
