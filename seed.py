#!/usr/bin/env python3
"""
seed.py — creates prerequisite source/dataset/geography rows and
one real seed observation (the same Thane Creek record from Day 1,
re-expressed against schema v0.2).

Run after init_db.py:
    python3 init_db.py && python3 seed.py
"""

from vana_db import get_conn, insert_observation, now

conn = get_conn()
cur = conn.cursor()

SOURCE_ID = "SRC-THANECREEK-2023-CARBONSTOCK-01"
cur.execute("SELECT 1 FROM source WHERE source_id=?", (SOURCE_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO source (source_id, source_type, title, publisher, url, citation,
                             retrieved_at, is_synthetic, notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        SOURCE_ID, "SCIENTIFIC_LITERATURE",
        "Standing carbon stock of Thane Creek mangrove ecosystem: An integrated approach using allometry and remote sensing techniques",
        "ScienceDirect / Regional Studies in Marine Science",
        "https://www.sciencedirect.com/science/article/abs/pii/S2352485523003973",
        "Standing carbon stock of Thane Creek mangrove ecosystem (2023), ScienceDirect, article id S2352485523003973.",
        now(), False,
        "UNCERTAIN: full author citation not yet confirmed — publisher page blocks automated access.",
    ))

RUN_ID = "RUN-2026-08-19-SEED-001"
cur.execute("SELECT 1 FROM processing_run WHERE run_id=?", (RUN_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO processing_run (run_id, source_id, dataset_id, pipeline_stage, status,
                                     input_ref, output_ref, error_detail, started_at, finished_at, actor)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (RUN_ID, SOURCE_ID, None, "SEED", "DONE",
          "ScienceDirect abstract (search snippet — full text paywalled)",
          "one dataset + one seed observation, schema v0.2", None, now(), now(),
          "Kavy (Day-6 build, init_db.py seed)"))

DATASET_ID = "DS-THANECREEK-CARBONSTOCK-2023-01"
cur.execute("SELECT 1 FROM dataset WHERE dataset_id=?", (DATASET_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO dataset (dataset_id, dataset_name, source_id, methodology,
                              schema_version, created_at, status)
        VALUES (?,?,?,?,?,?,?)
    """, (DATASET_ID, "Thane Creek mangrove above-ground biomass (2023 study)", SOURCE_ID,
          "Allometry, and allometry-remote-sensing (NDVI) integrated technique, across 10 stations along Thane Creek",
          "0.4", now(), "VALIDATED"))

GEO_ID = "GEO-THANECREEK-01"
cur.execute("SELECT 1 FROM geo_location WHERE geo_id=?", (GEO_ID,))
if not cur.fetchone():
    cur.execute("""
        INSERT INTO geo_location (geo_id, scope, place_name, lat, lon, crs, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (GEO_ID, "ZONE", "Thane Creek, Maharashtra, India", 19.2183, 72.9781, "EPSG:4326",
          "Zone-level centroid, not observation-specific — this seed record is literature-derived, "
          "not a Group 3 field capture, so a shared zone row is appropriate here per Decision B "
          "(observation-specific points are for field captures)."))

conn.commit()

OBS_ID = "OBS-THANECREEK-AGB-2023-01"
created, canonical_record_id = insert_observation(
    conn,
    observation_id=OBS_ID,
    dataset_id=DATASET_ID,
    geo_id=GEO_ID,
    observed_at="2023-01-01T00:00:00+00:00",  # date-only in source; no time-of-day available
    capture_method=None,  # literature source, not a field capture — correctly NULL, not guessed
    species="Avicennia marina",
    observation_type="BIOMASS",
    quality_status="VALIDATED",
    confidence="MEDIUM",  # from an abstract, not the full paper
    measurements=[
        {"metric_name": "above_ground_biomass", "value": 84.83, "unit": "Mg/ha",
         "method": "allometry", "original_value_text": "84.83"},
        {"metric_name": "above_ground_biomass", "value": 111.31, "unit": "Mg/ha",
         "method": "allometry_remote_sensing_integrated", "original_value_text": "111.31"},
    ],
    source_id=SOURCE_ID,
    run_id=RUN_ID,
    derivation_note="Extracted verbatim from source abstract; no transformation applied.",
    field_meta=None,  # no device/operator — this is a literature record, not a field capture
    raw_artifact=None,  # no raw artifact for a literature-derived record
)

print(f"[seed] Seed observation {OBS_ID}: {'created' if created else 'already existed (idempotent no-op)'}, canonical_record_id={canonical_record_id}")
conn.close()
