# FSI ISFR 2023 Forest Cover Architecture Proposal

## Decision

FSI ISFR 2023 is an official historical government dataset, not a Group 3
field observation. It must not be sent through `POST /observations`.

The implementation reuses the existing `source`, `dataset`, and
`processing_run` structures, and adds a
dedicated official forest-cover record table and API path. The existing
Group 3 observation contract remains unchanged.

## Supported source facts

- Source name: Forest Survey of India.
- Report/dataset: India State of Forest Report 2023 (ISFR 2023).
- Official URL: https://fsi.nic.in/forest-report-2023?pgID=forest-report-2023
- Assessment year: 2023.

Numeric values are not embedded in this repository's source material. The
fixture therefore carries null numeric values and is explicitly a test
fixture, not production data. An importer must reject a production record
whose required numeric values are absent unless the source extract documents
that the value is genuinely unavailable.

## Existing structures reused

| Concern | Existing structure | Use |
|---|---|---|
| Official source | `source` | `source_type = GOVERNMENT_DATASET`, publisher, URL, citation, retrieval time |
| Product registration | `dataset` | ISFR 2023 product identity, methodology, schema version, status |
| Processing lineage | `processing_run` | Import execution and source/dataset references |
| Provenance processing | `processing_run` | Import execution and source/dataset references |

The new record entity stores the official dataset row itself. It does not
create an `observation`, `field_observation_meta`, `raw_artifact`, or
observation-bound `provenance` row. Existing `raw_artifact` and `provenance`
rows require an observation foreign key, so using them would require a fake
Group 3 observation. The official record instead retains its required
`provenance_reference` and links to the existing source/dataset and import
run.

## Official record fields

Each record has:

- `record_id`: deterministic ID derived from dataset, geography, and row key.
- `dataset_id`: FK to the existing `dataset` row.
- `source_record_id`: source row/code, when supplied by FSI.
- `assessment_year`: integer year, required and preserved as supplied.
- `geography_level`: `STATE` or `DISTRICT`.
- `state`: required administrative name.
- `district`: required only for district records.
- `boundary_reference`: optional authoritative boundary/code reference; no fake coordinates.
- `forest_cover_area`, `forest_cover_percentage`, `very_dense_forest_area`,
  `moderately_dense_forest_area`, `open_forest_area`, `mangrove_area`:
  optional numeric values, preserved as null when not present in the source.
- `unit`: explicit unit for area values.
- `methodology`, `quality_status`, `provenance_reference`, and
  `source_url`.

The six measures are separate columns because the UI contract names them
explicitly and the source report distinguishes forest-cover classes. The
record is not a measurement-shaped Group 3 observation.

## Geography

The existing `geo_location` table is suitable for points and zones but does
not have structured State/District fields, and the API only creates points.
Official records therefore store `geography_level`, `state`, `district`, and
an optional `boundary_reference` on the official record. No latitude,
longitude, centroid, or polygon is invented. A later authoritative boundary
integration may populate a reference or geometry without changing the
meaning of Group 3 observations.

## API

- `POST /official/forest-cover`: idempotently imports one validated official record.
- `GET /official/forest-cover/{record_id}`: retrieves one record with source and provenance.
- `GET /datasets/{dataset_id}/forest-cover`: lists records for a dataset.

The POST uses a client-supplied `idempotency_key` or deterministic record
identity. An identical repeat returns the existing record; a conflicting
payload for the same identity is rejected. Existing `POST /observations`
behavior is not changed.

## Explicitly excluded Group 3 semantics

Official records do not require or accept fabricated `device_id`,
`sensor_id`, `flight_id`, `mission_id`, calibration, GNSS, synthetic state,
field-capture metadata, or observation timestamps. `external_api` is not used
for a static report. The official source category is `GOVERNMENT_DATASET`.

## Remaining extraction requirement

Before production import, extract and verify each numeric value, unit,
State/District row, source row identifier, reporting scope, and authoritative
boundary reference from the official FSI report. The repository fixture does
not assert any actual FSI number.