# GROUP 1 — T16 FINAL STATUS REPORT

**Date:** 2026-08-29  
**Issue ID:** T16 — `GROUP3_FIELD_CAPTURE` Source Type Classification  
**Author:** Group 1 Canonical Observation / Runtime Verification Engineer  
**Final Classification:** **PASS (RESOLVED)**

---

## 1. Problem Statement & Historical Context

Previously identified discrepancy:
> *T16 — GROUP3_FIELD_CAPTURE is rejected by current runtime validation / SQLite CHECK constraint, while the PostgreSQL target DDL explicitly allows it.*

In the PostgreSQL target DDL (`migrations/0001_init.sql`), the `source` table contains:
```sql
source_type TEXT NOT NULL CHECK (source_type IN
    ('SCIENTIFIC_LITERATURE','GOVERNMENT_DATASET','EARTH_OBSERVATION',
     'INSTITUTIONAL','SYNTHETIC_TEST','GROUP3_FIELD_CAPTURE'))
```

However, `src/vana_integrity/validation.py` historically omitted `GROUP3_FIELD_CAPTURE` from `VALID_SOURCE_TYPES`, causing genuine Group 3 field-capture observations to be rejected with HTTP 422.

---

## 2. Root Cause Analysis

- **Application Validation Omission:** `VALID_SOURCE_TYPES` in `src/vana_integrity/validation.py` contained only 5 items, omitting the 6th canonical source type `GROUP3_FIELD_CAPTURE`.
- **Classification Semantics:** `GROUP3_FIELD_CAPTURE` is a real-world physical capture source type (`is_synthetic = False`), distinct from `SYNTHETIC_TEST` (`is_synthetic = True`).

---

## 3. Implemented Fix & Contract Alignment

1. **Updated `VALID_SOURCE_TYPES` in `src/vana_integrity/validation.py`:**
   ```python
   VALID_SOURCE_TYPES = {
       "SCIENTIFIC_LITERATURE",
       "GOVERNMENT_DATASET",
       "EARTH_OBSERVATION",
       "INSTITUTIONAL",
       "SYNTHETIC_TEST",
       "GROUP3_FIELD_CAPTURE",
   }
   ```

2. **Synthetic / Physical Boundary Preservation:**
   - For `SYNTHETIC_TEST`: requires `is_synthetic = True` (persisted as `1`).
   - For `GROUP3_FIELD_CAPTURE`: allowed with `is_synthetic = False` (persisted as `0`).

---

## 4. Live Runtime Verification Evidence

### Test Execution:
```bash
python -c "import sys; sys.path.insert(0, 'src'); import tests.test_group1_verification as tg; tg.t16()"
```

### Result:
```text
TEST: T16 synthetic/physical classification boundary
INPUT:    GROUP3_FIELD_CAPTURE / SYNTHETIC_TEST / SCIENTIFIC_LITERATURE
EXPECTED: G3 field capture accepted (201); synthetic ok (201); literature ok (201, flag=0)
ACTUAL:   g3=201, syn=201, sci=201 flag=0
RESULT:   PASS
EVIDENCE:
  - GROUP3_FIELD_CAPTURE HTTP 201 (Postgres 0001_init.sql & validation.py accept it)
  - SYNTHETIC_TEST HTTP 201
  - SCIENTIFIC_LITERATURE HTTP 201, is_synthetic=0
```

### Six-Region Field Ingestion:
All 6 regional observations were ingested with `source_type: "GROUP3_FIELD_CAPTURE"` and `is_synthetic: False`. All 6 returned HTTP `201 Created` and persisted `is_synthetic = 0` accurately.

---

## 5. Conclusion & Enterprise Clearance

The `GROUP3_FIELD_CAPTURE` classification defect is **fully resolved**. The runtime validation matches the target production DDL and successfully ingests physical field observations.

**Verdict: PASS**
