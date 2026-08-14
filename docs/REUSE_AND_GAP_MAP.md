# VANA / PRAKRITI — GROUP 1
# REUSE AND GAP MAP

Status: PHASE 1 — LEARN / RECON COMPLETE
Date: 2026-08-13
Group: Group 1 — Data Foundation
Lead: Raj Prajapati

## 1. PURPOSE

This document consolidates the Phase 1 reconnaissance from:

- Kavy — canonical schema / MasterDB
- Rukkaiya — identity / provenance / idempotency
- Sanskar — ingestion / retrieval API
- Hemanth — Group 3 observation contract

Purpose:

1. Identify what existing VANA/BHIV capabilities can be reused.
2. Identify what is missing or not yet verified.
3. Resolve the Group 3 → Group 1 mapping boundary.
4. Establish the minimum BUILD scope.
5. Prevent duplicate or parallel implementations.

No implementation decision is treated as verified unless supported by existing
implementation, schema, runtime evidence, or an explicit agreed contract.


# 2. TARGET DATA FOUNDATION

Required Group 1 chain:

Schema
  ↓
Validation
  ↓
Observation Identity
  ↓
Persistence
  ↓
Provenance
  ↓
Idempotency
  ↓
Retrieval
  ↓
Group 3 Integration


Immediate acceptance condition:

A VANA observation fixture can be submitted through the canonical interface,
validated, assigned/verified an identity, persisted, retrieved with provenance,
and submitted again without creating a duplicate.


# 3. EXISTING CAPABILITIES — REUSE ASSESSMENT


## 3.1 Database / SQL Backend

### Existing capability

Existing MasterDB implementation uses:

- SQLAlchemy
- `MASTERDB_DATABASE_URL`
- SQLite for local development
- PostgreSQL through the same backend abstraction for production

### Decision

REUSE PATTERN.

The connection/backend abstraction is reusable.

### Do NOT reuse

The existing generic:

`artifact_records`

JSON-value table should NOT become the canonical VANA relational schema.

Existing reconnaissance found no normalized relational VANA schema in that
repository and no existing PostGIS implementation there.

### Status

REUSE PATTERN — VERIFIED


# 4. CANONICAL VANA SCHEMA


## 4.1 Existing VANA entities

The current VANA schema defines:

- source
- dataset
- geography
- observation
- measurement
- processing_run
- provenance
- schema_version

### Status

EXISTS / REUSABLE as current VANA foundation.


## 4.2 Source

Existing model supports:

- source identity
- source type
- title
- publisher
- URL
- citation
- retrieval timestamp
- synthetic flag
- notes

### Decision

REUSE.

No new source model required for the Group 3 observation path.


## 4.3 Dataset

Group 3 proposes a mission-level batch.

Current schema contains `dataset`.

### Decision

Dataset can represent the survey/mission grouping.

### Status

MAPPING SUPPORTED.

Final naming/semantics should be documented in the API contract.


## 4.4 Observation

Current observation model supports:

- observation ID
- dataset relationship
- geography relationship
- observation date
- observation type
- confidence
- conflict information
- creation timestamp

### Status

PARTIALLY COMPATIBLE WITH GROUP 3.


## 4.5 Measurement

Current model contains:

- measurement ID
- observation ID
- metric name
- value
- unit
- method
- original value text
- transformation information
- creation timestamp

### Decision

Observation → Measurement is ONE-TO-MANY.

A single observation may therefore have multiple measurements.

Example:

Observation:
`TC-Z03-F02-LIDAR-OBS001`

Measurement:
`canopy_height = 4.7 m`

### Status

VERIFIED / COMPATIBLE.


## 4.6 Geography

Current model provides geography records referenced by observations.

Group 3 currently describes geography as zone-level/named-place geography.

### Current mapping

Group 3 observation
        ↓
observation.geo_id
        ↓
geography

### Important limitation

Group 3's identity model treats coordinates as part of the observation identity.

The current zone-level geography model does not preserve unique per-observation
coordinates.

### Status

STRUCTURALLY SUPPORTED
SEMANTIC GAP REMAINS.


# 5. GROUP 3 → VANA FIELD MAPPING


| Group 3 field | Current VANA destination | Status |
|---|---|---|
| observation_id | observation.observation_id | SUPPORTED |
| device_id | No clear destination | GAP |
| timestamp | observation_date | GAP — DATE loses time-of-day |
| latitude | geography | PARTIAL — current geography is zone-level |
| longitude | geography | PARTIAL — current geography is zone-level |
| observation_type | observation.observation_type | SEMANTIC CONFLICT |
| measurement | measurement.value | SUPPORTED |
| unit | measurement.unit | SUPPORTED |
| accuracy | No clear destination | GAP |
| calibration_status | No clear destination | GAP |
| raw_artifact_reference | No clear canonical destination | GAP |
| quality_status | No clear destination | GAP |
| processing_status | No clear destination | GAP |
| provenance | provenance / processing_run | PARTIAL / requires mapping |


# 6. IMPORTANT GROUP 3 GAPS


## 6.1 Device identity

Group 3 requires `device_id`.

The current canonical schema does not provide a clear observation-level
destination for it.

### Status

GAP.

### Requirement

Do not invent a device field without an approved schema decision.

Group 3 has indicated that device registration is expected to use the existing
capability registry rather than a parallel device inventory.


## 6.2 Timestamp precision

Group 3 emits ISO-8601 UTC timestamps such as:

`2026-08-13T09:14:22Z`

The current observation model uses a date-level field.

### Problem

Time-of-day is lost.

This is significant for an intertidal observation because observations at
different times can reflect different tidal conditions.

### Status

GAP.

### Decision required

Canonical observation timestamp representation must preserve capture time.


## 6.3 Per-observation coordinates

Group 3 identity includes GPS coordinates.

Current geography is zone-oriented.

### Problem

Multiple observations in the same zone could resolve to the same geography
record and therefore lose the observation-specific coordinates.

### Status

GAP / DECISION REQUIRED.

Do not assume that zone geography is sufficient for field observations.


## 6.4 Accuracy

Group 3 requires:

`accuracy`

Group 3 currently has no measured accuracy figures.

Correct current value:

`NOT VERIFIED`

Do not substitute an invented numeric accuracy.

### Status

GAP in canonical storage.


## 6.5 Calibration status

Group 3 requires:

`calibration_status`

Current Group 3 state:

`NOT VERIFIED`

### Status

GAP in canonical storage.


## 6.6 Raw artifact reference

Group 3 requires a reference to the preserved original artifact.

The field workflow requires preservation of original images, videos, sensor
readings and other raw evidence.

### Status

GAP / requires explicit canonical mapping.

The raw artifact itself should not be silently replaced by a derived output.


## 6.7 Quality status

Group 3 requires:

RAW
CAPTURED
VALIDATED
REJECTED
UNCERTAIN
INGESTED

Current canonical observation model does not provide a clearly established
destination.

### Status

GAP.


## 6.8 Processing status

Group 3 requires processing-stage information.

Current canonical processing information exists through `processing_run`, but
the exact Group 3 → processing_run mapping has not yet been formally defined.

### Status

PARTIAL / DECISION REQUIRED.


## 6.9 Observation type

Group 3 uses:

- aerial
- ground
- sensor
- site_evidence

The existing VANA `observation_type` has a potentially different semantic
meaning.

### Decision

Do NOT blindly map the Group 3 value into the existing field.

Semantic corruption of existing consumers must be avoided.

### Status

SEMANTIC GAP / DECISION REQUIRED.


# 7. OBSERVATION IDENTITY


## Group 3 authoritative model

Example:

`TC-Z03-F02-LIDAR-OBS001`

Identity consists of:

- Survey ID
- Zone ID
- Flight ID
- Sensor ID
- Observation sequence
- plus timestamp/coordinates as part of the broader identity model

Group 3 has stated that it will send a globally unique observation ID.

### Current Group 1 requirement

The observation ID must be stable across retries.

The same observation must not receive a new identity during retransmission.

### Status

IDENTITY MODEL RECEIVED.

### Open point

Group 3 still has an internal question about whether survey/date information is
encoded in the Survey ID or whether uniqueness depends on the composite plus
timestamp.

This must be resolved before treating the identity contract as permanently
closed.


# 8. IDEMPOTENCY


## Required behaviour

For:

`OBSERVATION-001`

the expected sequence is:

Before = 0

First submission = 1

Second identical submission = 1

After = 1


NOT:

0 → 1 → 2


## Existing evidence

Existing persistence demonstrates stable database-level identity behaviour,
but an explicit consumer-level idempotency contract has not yet been fully
established.

Previous demonstration evidence showed a row-count discrepancy during the
idempotency test.

### Decision

Idempotency must be explicitly implemented and tested at the canonical
ingestion boundary.

### Required test

Submit the exact same observation twice through the Group 1 API.

Expected:

canonical records = 1

after both submissions.


### Status

BUILD REQUIRED.


# 9. PROVENANCE


## Existing capabilities

Current VANA model includes:

- source
- processing_run
- provenance
- measurement relationship

This supports a source/processing lineage model.

### Group 3 required provenance

Group 3 expects traceability across:

Device
→ Operator
→ Mission
→ Observation
→ Raw Artifact
→ QA
→ Processing
→ Ingestion


### Status

PARTIAL.

### Gap

The exact mapping of device, operator, mission, raw artifact and QA evidence
into canonical provenance is not fully established.

### Requirement

Do not lose provenance at the API boundary.


# 10. RAW ARTIFACT


Group 3 requires:

- preserved original artifact
- artifact path/URI
- checksum where available
- relationship to the observation

The raw file itself is not sent as the canonical observation payload.

### Status

GAP / BUILD REQUIRED.

### Required outcome

The canonical observation must retain a durable reference to its raw evidence.


# 11. API / CONSUMER BOUNDARY


## Existing evidence

Database-level insertion and retrieval are demonstrated.

However, no authoritative consumer-facing ingestion/retrieval API was verified
in the supplied reconnaissance artifacts.

### Therefore

DO NOT treat direct database insertion as the Group 3 integration interface.

### Required API

Group 1 must provide/adapt:

1. Observation ingestion
2. Validation
3. Canonical persistence
4. Observation retrieval
5. Deterministic response
6. Provenance preservation
7. Idempotent resubmission behaviour

### Status

BUILD / VERIFY EXISTING RUNTIME FIRST.


# 12. VANA / SVACS TRACE CONTRACT


The authoritative SVACS payload and trace propagation contract was not verified
during Phase 1.

### Decision

Obtain the existing runtime contract before creating a replacement.

### Status

VERIFY / DEPENDENCY.


# 13. SYNTHETIC TEST FIXTURE


Group 3 has proposed using an explicitly synthetic fixture for the first
round-trip.

The fixture must remain clearly marked:

`SYNTHETIC_TEST`

and/or:

`is_synthetic = true`

### Purpose

The synthetic fixture may be used to prove:

- identity
- grouping
- validation
- persistence
- retrieval
- provenance
- idempotency

### Restriction

It must never be represented as a real field observation.

Group 3 has explicitly stated that no real sensor reading currently exists.


# 14. REUSE / ADAPT / BUILD MATRIX


| Capability | Decision |
|---|---|
| SQLAlchemy/Postgres backend pattern | REUSE |
| `MASTERDB_DATABASE_URL` pattern | REUSE |
| Generic artifact_records schema | DO NOT REUSE as canonical VANA schema |
| VANA normalized tables | USE / ADAPT |
| Source model | REUSE |
| Dataset model | REUSE / ADAPT |
| Measurement relationship | REUSE |
| Geography | ADAPT |
| Observation identity | BUILD / FORMALIZE |
| Per-observation timestamp | ADAPT |
| Per-observation coordinates | ADAPT |
| Device metadata | BUILD / DECISION |
| Accuracy | BUILD / DECISION |
| Calibration status | BUILD / DECISION |
| Raw artifact reference | BUILD / ADAPT |
| Quality status | BUILD / DECISION |
| Processing status | ADAPT |
| Provenance | ADAPT / COMPLETE |
| Idempotency | BUILD / PROVE |
| Ingestion API | VERIFY EXISTING → ADAPT/BUILD |
| Retrieval API | VERIFY EXISTING → ADAPT/BUILD |
| SVACS contract | VERIFY |
| Group 3 integration fixture | READY FOR BUILD/TEST |


# 15. ARCHITECTURE DECISIONS REQUIRED BEFORE BUILD


## Decision A — Field observation metadata

Two approaches identified:

### Option 1
Add required field-observation metadata directly to the canonical observation
model.

### Option 2
Create:

`field_observation_meta`

keyed by `observation_id`.

Hemanth has stated that Group 3 has no preference between these shapes.

### Decision owner

Raj + Kavy + Rukkaiya + Sanskar

Must be explicitly agreed before implementation.


## Decision B — Geography

Determine whether:

- zone-level geography remains the canonical geography reference, while
  observation-specific coordinates are separately retained,

OR

- geography becomes observation-specific.

Do not silently overload zone-level geography with observation-point meaning.


## Decision C — Timestamp

The canonical model must preserve full capture timestamp, including time of
day and timezone/UTC semantics.


## Decision D — Observation type

Resolve the semantic mismatch before mapping Group 3's
`aerial/ground/sensor/site_evidence` values.


## Decision E — Idempotency key

Define the canonical idempotency mechanism at the API boundary.

It must survive retries and produce:

`0 → 1 → 1`


# 16. BUILD ASSIGNMENT AFTER DECISIONS


## KAVY — Schema / Database

Build/adapt:

- approved schema changes
- migrations/versioning
- geography/time representation
- field metadata destination
- schema documentation
- fixture data


## RUKKAIYA — Integrity / Provenance / Idempotency

Build/prove:

- observation identity
- duplicate detection
- idempotent submission
- retry handling
- provenance preservation
- raw artifact reference
- malformed/incomplete observation failure behaviour
- integrity tests


## SANSKAR — API / Integration

Build/adapt:

- canonical ingestion endpoint
- request validation
- canonical write
- retrieval endpoint
- deterministic responses
- Group 3 consumer fixture
- API documentation
- integration test


## RAJ — Lead / Architecture / Integration

Own:

- architecture decisions
- convergence
- cross-member integration
- dependency resolution
- Group 3 coordination
- final acceptance test
- final handover


# 17. GROUP 3 INTEGRATION TARGET


Target:

Group 3 observation
        ↓
Group 1 API
        ↓
Validation
        ↓
Identity
        ↓
Canonical persistence
        ↓
Provenance + raw reference
        ↓
Retrieval
        ↓
Submit same observation
        ↓
No duplicate


# 18. REQUIRED TESTS


Minimum tests:

1. Valid observation
2. Missing required field
3. Malformed observation
4. Unknown device
5. Duplicate observation
6. Retry after failure
7. Provenance preservation
8. Retrieval
9. Raw-artifact reference
10. Deterministic response
11. Concurrent duplicate submission where practical


# 19. PHASE 2 ENTRY CRITERIA


BUILD may begin only after:

- [ ] Reuse decisions agreed
- [ ] Field metadata destination agreed
- [ ] Geography strategy agreed
- [ ] Timestamp strategy agreed
- [ ] Observation type semantics resolved
- [ ] Provenance mapping agreed
- [ ] Idempotency mechanism agreed
- [ ] API boundary identified or explicitly approved for implementation
- [ ] Group 3 fixture available
- [ ] No parallel/replacement database is being created


# 20. ACCEPTANCE GATE


Group 1 is accepted only when the complete chain is demonstrated:

REAL / APPROVED TEST OBSERVATION
        ↓
GROUP 1 API
        ↓
VALIDATION
        ↓
ASSIGN / VERIFY ID
        ↓
CANONICAL PERSISTENCE
        ↓
PROVENANCE
        +
RAW ARTIFACT REFERENCE
        ↓
RETRIEVAL
        ↓
SUBMIT SAME RECORD
        ↓
NO DUPLICATE


Expected idempotency:

0 → 1 → 1


# 21. CURRENT PHASE STATUS


PHASE 1 — LEARN / RECON

Kavy:       COMPLETE
Rukkaiya:   COMPLETE
Sanskar:    COMPLETE / PARTIAL INTERFACE VERIFICATION
Hemanth:    GROUP 3 CONTRACT RECEIVED
Raj:        CONSOLIDATION

Overall:

PHASE 1 COMPLETE FOR CONSOLIDATION.

PHASE 2 — BUILD:

NOT YET AUTHORIZED UNTIL ARCHITECTURE DECISIONS ARE AGREED.


# 22. PRINCIPLE

No capability is marked complete merely because a document describes it.

Implementation claims require executable/runtime evidence.

No local SQLite proof is treated as production VM verification.

No synthetic fixture is treated as real scientific data.

No schema field is invented merely to make integration convenient.

No duplicate implementation should be created where an existing capability can
be reused.

The final objective is a reproducible, consumer-usable VANA Data Foundation.
