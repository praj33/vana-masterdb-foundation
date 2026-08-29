"""Minimal FastAPI ingestion boundary."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from starlette.responses import JSONResponse

from vana_integrity.db import apply_schema, connect
from vana_integrity.idempotency import IdempotencyConflictError
from vana_integrity.ingestion import ingest_observation, retrieve_observation
from vana_integrity.validation import ValidationError

app = FastAPI(title="VANA Integrity Ingestion", version="0.1.1")


def create_app(
    database_url: str = ":memory:",
    conn: sqlite3.Connection | None = None,
) -> tuple[FastAPI, sqlite3.Connection]:
    """Build an app bound to the given database."""
    owned_conn = conn is None
    if conn is None:
        conn = connect(database_url)
        apply_schema(conn)

    test_app = FastAPI(title="VANA Integrity Ingestion", version="0.1.1")

    @test_app.on_event("shutdown")
    def _shutdown() -> None:
        if owned_conn:
            conn.close()

    @test_app.post("/ingest/observations")
    async def ingest_observations(
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> JSONResponse:
        body = await request.json()
        try:
            result = ingest_observation(conn, body, idempotency_key=idempotency_key)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
        except IdempotencyConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"message": str(exc), "idempotency_key": exc.idempotency_key},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"message": str(exc)}) from exc

        status_code = result.pop("http_status", 200)
        return JSONResponse(content={**result, "status": "ok"}, status_code=status_code)

    @test_app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "healthy", "service": "VANA Integrity Ingestion", "version": "0.1.1"}

    @test_app.get("/observations/{observation_id}")
    @test_app.get("/ingest/observations/{observation_id}")
    async def get_observation(observation_id: str) -> JSONResponse:
        obs = retrieve_observation(conn, observation_id)
        if obs is None:
            raise HTTPException(
                status_code=404,
                detail={"message": f"Observation '{observation_id}' not found", "status": "NOT_FOUND"},
            )
        return JSONResponse(content={"status": "ok", "observation": obs}, status_code=200)

    return test_app, conn


@app.post("/ingest/observations")
async def ingest_observations_default(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=503,
        detail="Use create_app(database_url) for a configured ingestion service",
    )
