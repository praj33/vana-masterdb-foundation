"""Request-level ingestion idempotency via Idempotency-Key and body fingerprinting.

Canonical Fingerprinting Contract:
- Normalized body: Canonical JSON via json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
- Transport headers, Idempotency-Key, and server timestamps are excluded.
- Algorithm: SHA-256 (utf-8 encoded digest)
- Table: idempotency_record (idempotency_key, observation_id, request_fingerprint, fingerprint_algorithm, first_response_status, created_at)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any


class IdempotencyConflictError(Exception):
    """Same idempotency key reused with a different request body."""

    def __init__(self, idempotency_key: str) -> None:
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Idempotency-Key '{idempotency_key}' was already used with a different request body"
        )


def normalize_request_body(body: dict[str, Any]) -> str:
    """Return a stable JSON representation for fingerprinting."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def compute_request_fingerprint(body: dict[str, Any]) -> str:
    """SHA-256 hex digest of the normalized request body."""
    normalized = normalize_request_body(body)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_idempotency(
    conn: sqlite3.Connection,
    idempotency_key: str | None,
    request_fingerprint: str,
) -> dict[str, Any] | None:
    """Return prior result when key+fingerprint match; raise IdempotencyConflictError on conflict."""
    if not idempotency_key:
        return None

    row = conn.execute(
        """
        SELECT idempotency_key, observation_id, request_fingerprint, fingerprint_algorithm, first_response_status
        FROM idempotency_record
        WHERE idempotency_key = ?
        """,
        (idempotency_key,),
    ).fetchone()

    if row is None:
        return None

    stored_fingerprint = row["request_fingerprint"]
    if stored_fingerprint != request_fingerprint:
        raise IdempotencyConflictError(idempotency_key)

    return {
        "observation_id": row["observation_id"],
        "first_response_status": row["first_response_status"],
        "http_status": 200,
        "idempotent": True,
    }


def record_idempotency(
    conn: sqlite3.Connection,
    idempotency_key: str | None,
    observation_id: str,
    request_fingerprint: str,
    first_response_status: str = "201",
    fingerprint_algorithm: str = "sha256",
) -> None:
    """Persist idempotency record into idempotency_record table."""
    if not idempotency_key:
        return

    conn.execute(
        """
        INSERT INTO idempotency_record (
            idempotency_key, observation_id, request_fingerprint,
            fingerprint_algorithm, first_response_status, created_at
        ) VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            idempotency_key,
            observation_id,
            request_fingerprint,
            fingerprint_algorithm,
            str(first_response_status),
        ),
    )

