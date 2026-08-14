# Kavy — Day 6 EOD Deliverable
## Canonical Schema & Database Engineer

**Date:** 19 August 2026
**For:** Raj (integration), Rukkaiya, Sanskar, Hemanth

---

## Against the acceptance test

> *"A fresh engineer must be able to initialise the database and
> create/retrieve a VANA observation without manually editing the
> database."*

**Met — proven twice in the same session.** `python3 init_db.py &&
python3 seed.py && python3 test_roundtrip.py` runs clean from empty,
and re-running `init_db.py && seed.py` afterward is a correct no-op
(evidence in `EVIDENCE.txt`, both runs captured).

---

## Deliverables checklist

| # | Required | Status | Where |
|---|---|---|---|
| 1 | Working database schema | **DONE** | `migrations/0001_init.sql` (Postgres/PostGIS target) |
| 2 | Migration/init mechanism | **DONE — built from zero.** Recon (Day 5) found no migration tooling existed anywhere in MasterDB. `init_db.py` is new: tracks applied migrations in `_migrations_log`, safe to re-run. | `init_db.py` |
| 3 | Seed/test record | **DONE** — real Thane Creek record (not synthetic) | `seed.py` |
| 4 | Working insert + retrieval | **DONE** | `vana_db.py` (`insert_observation`, `retrieve_observation`) |
| 5 | Schema documentation/data dictionary | **DONE** | `DATA_DICTIONARY.md` |
| 6 | Reproducible setup command | **DONE** — `python3 init_db.py && python3 seed.py` | see above |
| 7 | Evidence of DB creation + retrieval | **DONE** | `EVIDENCE.txt` |

---

## What changed since Day 1's v0.1 schema

Implements architecture decisions A–D agreed in the `REUSE_AND_GAP_MAP.md`
review, plus the `raw_artifact` table:

- **A:** `field_observation_meta` — separate table, not columns on `observation`
- **B:** `geography.scope` (`POINT`/`ZONE`) — field captures get their own point; literature/aggregate records may share a zone
- **C:** `observation_date` → `observed_at`, full `TIMESTAMPTZ`
- **D:** new `capture_method` column; `observation_type` untouched, no semantic overload
- **New:** `raw_artifact` table — Kavy owns the table shape, Rukkaiya owns the hashing/integrity logic that populates `content_hash`

## Idempotency (co-owned with Rukkaiya's identity/provenance layer)

`observation_id` is caller-supplied and is the idempotency key —
directly uses Group 3's own stable ID format
(`TC-Z03-F02-LIDAR-OBS001`), no translation layer. Proven in
`test_roundtrip.py`: **0 → 1 → 1 → 1** across three identical
submissions of a Group-3-shaped fixture, explicitly marked
`SYNTHETIC/TEST` per the team's synthetic-data rule.

## Invalid-record rejection

Actually triggered, not asserted: an observation with a missing
required `dataset_id` was submitted; the real database error
(`NOT NULL constraint failed: observation.dataset_id`) was captured in
`EVIDENCE.txt`.

---

## Honesty flags — read before treating this as done

- **Not run against the real VM Postgres/PostGIS.** No network path to
  it from this environment. `migrations/0001_init.sql` is the literal
  file to run there — table shapes are field-identical to the SQLite
  proof, but this is the one thing standing between this being fully
  verified and being verified-on-a-stand-in. This is the same caveat
  as Day 1; it has not been resolved since.
- **Samachar → MasterDB integration is still not part of this path.**
  Everything here is direct insert via `vana_db.py` — Sanskar's
  ingestion API is the layer that will actually receive Group 3
  submissions. This proves the database side is ready to be called by
  that API; it isn't the API itself.
- **`geography.scope` discipline is convention, not a DB constraint** —
  flagged in the data dictionary, worth tightening before Group 3
  integration goes live.

---

## For Raj's integration

`vana_db.py`'s `insert_observation()` / `retrieve_observation()` are
the functions Sanskar's API layer should call directly — they already
handle idempotency, field-observation metadata, and raw-artifact
linkage. No need to reimplement insert logic at the API layer, just
call these against the same `VANA_DATABASE_URL`.

**Files delivered:** `migrations/0001_init.sql`,
`migrations/0001_init_sqlite.sql`, `init_db.py`, `vana_db.py`,
`seed.py`, `test_roundtrip.py`, `DATA_DICTIONARY.md`, `EVIDENCE.txt`.
