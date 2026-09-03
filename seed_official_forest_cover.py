#!/usr/bin/env python3
"""
seed_official_forest_cover.py — Seeds verified official FSI ISFR 2023 records
from data/fsi/isfr_2023_maharashtra.json into the configured VANA database.

Supports both PostgreSQL and SQLite backends via VANA_DATABASE_URL.
Execution is strictly idempotent (REPLAY on repeat).
"""

import json
from pathlib import Path

from api.models import OfficialForestCoverRequest
from api.official_forest_cover import persist_official_forest_cover


def seed_official_forest_cover():
    repo_root = Path(__file__).resolve().parent
    data_path = repo_root / "data" / "fsi" / "isfr_2023_maharashtra.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Official FSI data file not found: {data_path}")

    data = json.loads(data_path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    print(f"[seed_official_forest_cover] Found {len(records)} record(s) in {data_path.name}")

    for idx, raw_record in enumerate(records, start=1):
        model = OfficialForestCoverRequest.model_validate(raw_record)
        res = persist_official_forest_cover(model.model_dump())
        print(
            f"[seed_official_forest_cover] [{idx}/{len(records)}] "
            f"record_id={res.get('record_id')} status={res.get('status')} (HTTP {res.get('http_status')})"
        )


if __name__ == "__main__":
    seed_official_forest_cover()
