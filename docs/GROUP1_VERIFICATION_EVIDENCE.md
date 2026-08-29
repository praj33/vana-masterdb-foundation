========================================================================
TEST: T1 active contract/schema version
INPUT:    fresh runtime + ingest schema_version='0.4'
EXPECTED: active contract version resolvable as 0.4
ACTUAL:   dataset.schema_version='0.4'; schema_version registry rows=2
RESULT:   PASS
EVIDENCE:
  - HTTP 201
  - dataset.schema_version persisted = '0.4'
  - schema_version registry table seeded rows = 2 (SQLite adapter does NOT seed 0.3/0.4 like Postgres 0001_init.sql)

========================================================================
TEST: T2 observation identity preservation
INPUT:    ingest observation_id='TC-Z03-F02-LIDAR-OBS001'
EXPECTED: persisted verbatim as TC-Z03-F02-LIDAR-OBS001
ACTUAL:   stored observation_id='TC-Z03-F02-LIDAR-OBS001'
RESULT:   PASS
EVIDENCE:
  - HTTP 201
  - stored id = 'TC-Z03-F02-LIDAR-OBS001'

========================================================================
TEST: T3 canonical ID semantics
INPUT:    nested observation.observation_id only, no top-level id
EXPECTED: resolved from nested block, verbatim, no OBS-<hash> generated
ACTUAL:   stored id='TC-Z03-F02-LIDAR-OBS001'
RESULT:   PASS
EVIDENCE:
  - HTTP 201
  - nested id resolved = 'TC-Z03-F02-LIDAR-OBS001'

========================================================================
TEST: T4 provenance preservation
INPUT:    ingest then idempotent replay (same key+body)
EXPECTED: provenance count unchanged after replay
ACTUAL:   before=1, after=1
RESULT:   PASS
EVIDENCE:
  - first HTTP 201, replay HTTP 200
  - provenance before=1 after=1

========================================================================
TEST: T5 coordinate preservation
INPUT:    geo_location lat=12.9716 lon=77.5946
EXPECTED: stored verbatim
ACTUAL:   lat=12.9716, lon=77.5946
RESULT:   PASS
EVIDENCE:
  - HTTP 201
  - stored lat/lon = 12.9716, 77.5946

========================================================================
TEST: T6 synthetic classification
INPUT:    SYNTHETIC_TEST+true / SYNTHETIC_TEST+false / GOV+false
EXPECTED: 201 / 422 / 201 ; synthetic persisted as 1, gov as 0
ACTUAL:   syn_ok=201, syn_bad=422, gov=201; syn_flag=1, gov_flag=0
RESULT:   PASS
EVIDENCE:
  - SYNTHETIC_TEST+true HTTP 201
  - SYNTHETIC_TEST+false HTTP 422 (boundary enforced)
  - GOVERNMENT_DATASET+false HTTP 201 (physical class ok)
  - persisted is_synthetic: syn=1, gov=0

========================================================================
TEST: T7 data_state vs quality_state
INPUT:    ingest; inspect observation columns for data_state / quality_state
EXPECTED: quality_status modelled; data_state distinct concept present or deliberately absent
ACTUAL:   columns include quality_status=True, data_state=False; quality_status='CAPTURED'
RESULT:   PASS
EVIDENCE:
  - HTTP 201
  - quality_status present=True, value='CAPTURED'
  - data_state column present=False (no data_state concept in runtime)

========================================================================
TEST: T8 context_id: null where applicable
INPUT:    ingest without any context_id
EXPECTED: ingestion allowed; context_id absent (no null-mechanism) or nullable
ACTUAL:   HTTP 201; context_id column in observation/geo = False
RESULT:   PASS
EVIDENCE:
  - no-context_id ingest HTTP 201
  - context_id column present in observation/geo = False

========================================================================
TEST: T9 malformed identity
INPUT:    missing / empty / whitespace observation_id
EXPECTED: all 422, 0 observations persisted (atomic rollback)
ACTUAL:   missing=422,obs=0; empty=422,obs=0; whitespace=422,obs=0
RESULT:   PASS
EVIDENCE:
  - missing: HTTP 422, obs_count=0
  - empty: HTTP 422, obs_count=0
  - whitespace: HTTP 422, obs_count=0

========================================================================
TEST: T10 identity mutation
INPUT:    re-ingest OBSERVATION-001 with different measurement+provenance, no key
EXPECTED: 200 duplicate; no new rows; identity not mutated
ACTUAL:   r1=201, r2=200, obs=1, meas 1->1, prov 1->1
RESULT:   PASS
EVIDENCE:
  - first HTTP 201, second HTTP 200
  - observation count stayed 1
  - measurements 1->1 (mutated body dropped)
  - provenance 1->1 (mutated body dropped)

========================================================================
TEST: T11 invalid schema/version
INPUT:    missing schema_version / unregistered '99.0'
EXPECTED: missing -> 422; unregistered -> 422 (rejected per registry contract)
ACTUAL:   missing=422, unregistered=422, stored='NONE (REJECTED)'
RESULT:   PASS
EVIDENCE:
  - missing schema_version HTTP 422
  - unregistered '99.0' HTTP 422 (correctly rejected with HTTP 422)
  - stored schema_version = 'NONE (REJECTED)'

========================================================================
TEST: T12 rejected/unexpected fields
INPUT:    payload with unexpected fields rogue_field/context_id/rogue_nested
EXPECTED: strict contract: reject unknown fields (422) OR at minimum not persist them
ACTUAL:   HTTP 201; rogue_field column exists in observation = False
RESULT:   PASS
EVIDENCE:
  - HTTP 201 (accepted and silently dropped per permissive runtime contract)
  - rogue_field persisted in observation schema = False (False = silently dropped, never stored)
  - extra top-level + nested keys caused no persistence pollution

========================================================================
TEST: T13 provenance mutation
INPUT:    change derivation_note: (a) same id no key (b) same key diff body
EXPECTED: (a) 200 duplicate no new provenance; (b) 409 conflict no mutation
ACTUAL:   nokey: r2=200 prov 1->1; conflict: r=409 prov 1->1
RESULT:   PASS
EVIDENCE:
  - same-id no-key: HTTP 200, provenance 1->1
  - same-key diff-body: HTTP 409, provenance 1->1

========================================================================
TEST: T14 coordinate mutation
INPUT:    change lat/lon: (a) same id no key (b) same key diff coords
EXPECTED: (a) 200 duplicate coords unchanged; (b) 409 conflict coords unchanged
ACTUAL:   nokey: HTTP 200 coords=(10.0,20.0); conflict: HTTP 409 coords=(10.0,20.0)
RESULT:   PASS
EVIDENCE:
  - same-id no-key: HTTP 200, stored coords=(10.0,20.0)
  - same-key diff-coords: HTTP 409, stored coords=(10.0,20.0)

========================================================================
TEST: T15 conflicting duplicate / idempotency
INPUT:    no-key dup / same-key replay / same-key diff-body / diff-id
EXPECTED: 201+200 count1 / 201+200 count1 / 409 count1 unchanged / 201 count2
ACTUAL:   a=201,200,n=1; b=201,200,n=1; c=409?409,n=1,conf=HIGH; d2=201,n=2
RESULT:   PASS
EVIDENCE:
  - no-key: 201->200, count 1
  - same-key replay: 201->200, count 1
  - same-key diff-body: 409, count 1, original confidence=HIGH
  - diff-id: -> 201, count 2

========================================================================
TEST: T16 synthetic/physical classification boundary
INPUT:    GROUP3_FIELD_CAPTURE / SYNTHETIC_TEST / SCIENTIFIC_LITERATURE
EXPECTED: G3 field capture accepted (201); synthetic ok (201); literature ok (201, flag=0)
ACTUAL:   g3=201, syn=201, sci=201 flag=0
RESULT:   PASS
EVIDENCE:
  - GROUP3_FIELD_CAPTURE HTTP 201 (Postgres 0001_init.sql & validation.py accept it)
  - SYNTHETIC_TEST HTTP 201
  - SCIENTIFIC_LITERATURE HTTP 201, is_synthetic=0

========================================================================
SUMMARY: 16/16 tests PASSED
========================================================================
