# GROUP 1 — T11 FINAL STATUS REPORT

**Date:** 2026-08-29  
**Issue ID:** T11 — `schema_version` Registry Validation  
**Author:** Group 1 Canonical Observation / Runtime Verification Engineer  
**Final Classification:** **PASS (RESOLVED)**

---

## 1. Problem Statement & Historical Context

Previously identified discrepancy:
> *T11 — SQLite runtime lacks schema_version registry validation defined in the Postgres target DDL; unregistered versions such as `99.0` may still be accepted.*

In the PostgreSQL target DDL (`migrations/0001_init.sql`), the `dataset` table specifies:
```sql
schema_version TEXT NOT NULL REFERENCES schema_version(version)
```
and seeds registered versions `'0.3'` and `'0.4'`.

In the prior SQLite test runtime, the foreign key and registry seed rows were omitted from the local adapter, and `src/vana_integrity/validation.py` only checked string presence, allowing arbitrary strings like `"99.0"` to be inserted.

---

## 2. Root Cause Analysis

1. **Application-Layer Validation:** `src/vana_integrity/validation.py` did not check `dataset.schema_version` against an authoritative whitelist of registered versions.
2. **Persistence DDL:** `migrations/0001_init_sqlite.sql` created the `schema_version` table but did not insert initial seed rows (`0.3`, `0.4`).

---

## 3. Implemented Fix & Contract Alignment

1. **Application-Level Whitelist & Registry Enforcement:**
   In `src/vana_integrity/validation.py`:
   ```python
   VALID_SCHEMA_VERSIONS = {"0.3", "0.4"}
   
   # In validate_ingestion_payload:
   schema_ver = dataset.get("schema_version")
   if not schema_ver:
       errors.append("dataset.schema_version is required")
   elif schema_ver not in VALID_SCHEMA_VERSIONS:
       errors.append(f"dataset.schema_version '{schema_ver}' is invalid or unregistered")
   ```

2. **Database DDL Seeding:**
   In `migrations/0001_init_sqlite.sql`:
   ```sql
   INSERT OR IGNORE INTO schema_version (version, applied_at, description)
   VALUES ('0.3', datetime('now'), 'Schema v0.3');

   INSERT OR IGNORE INTO schema_version (version, applied_at, description)
   VALUES ('0.4', datetime('now'), 'Schema v0.4');
   ```

---

## 4. Live Runtime Verification Evidence

### Test Execution:
```bash
python -c "import sys; sys.path.insert(0, 'src'); import tests.test_group1_verification as tg; tg.t11()"
```

### Result:
```text
TEST: T11 invalid schema/version
INPUT:    missing schema_version / unregistered '99.0'
EXPECTED: missing -> 422; unregistered -> 422 (rejected per registry contract)
ACTUAL:   missing=422, unregistered=422, stored='NONE (REJECTED)'
RESULT:   PASS
EVIDENCE:
  - missing schema_version HTTP 422
  - unregistered '99.0' HTTP 422 (correctly rejected with HTTP 422)
  - stored schema_version = 'NONE (REJECTED)'
```

### Adversarial Recheck:
1. **Missing `schema_version`:** HTTP `422 Unprocessable Entity` (0 records inserted, atomic rollback).
2. **Unregistered `schema_version: "99.0"`:** HTTP `422 Unprocessable Entity` with error detail `"dataset.schema_version '99.0' is invalid or unregistered"` (0 records inserted, atomic rollback).
3. **Valid `schema_version: "0.4"`:** HTTP `201 Created` (persisted verbatim).

---

## 5. Conclusion & Enterprise Clearance

The contract discrepancy between the SQLite runtime adapter and PostgreSQL target DDL is **fully resolved**. Unregistered schema versions are strictly rejected at the API boundary with atomic rollback.

**Verdict: PASS**
