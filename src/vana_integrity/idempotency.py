"""Request-level ingestion idempotency via Idempotency-Key and body fingerprint."""

from __future__ import annotations

import hashlib
import json
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
    conn,
    idempotency_key: str | None,
    request_fingerprint: str,
) -> dict[str, Any] | None:
    """Return a prior result when key+fingerprint match; raise on key conflict."""
    if not idempotency_key:
        return None

    row = conn.execute(
        """
        SELECT idempotency_key, observation_id, request_fingerprint, http_status
        FROM ingestion_idempotency
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
        "http_status": row["http_status"],
        "idempotent": True,
    }


def record_idempotency(
    conn,
    idempotency_key: str | None,
    observation_id: str,
    request_fingerprint: str,
    http_status: int,
) -> None:
    if not idempotency_key:
        return

    conn.execute(
        """
        INSERT INTO ingestion_idempotency (
            idempotency_key, observation_id, request_fingerprint, http_status
        ) VALUES (?, ?, ?, ?)
        """,
        (idempotency_key, observation_id, request_fingerprint, http_status),
    )
