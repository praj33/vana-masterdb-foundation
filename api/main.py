from uuid import uuid4
from api.adapters import adapt_v21_to_canonical
from api.validation_v21 import validate_v21_observation

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.models import (
    ErrorResponse,
    IngestionResponse,
    ObservationRequest,
    RetrievalResponse,
)
from api.persistence import (
    persist_observation,
    retrieve_observation as retrieve_persisted_observation,
)
from api.validation import validate_observation


app = FastAPI(
    title="VANA MasterDB Observation API",
    version="1.0.0",
    description="Consumer-facing Group 3 observation ingestion and retrieval API.",
)


def _trace_id() -> str:
    return f"VANA-{uuid4().hex[:12]}"


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "service": "VANA MasterDB Observation API",
        "version": "1.0.0",
    }


@app.post(
    "/observations",
    response_model=IngestionResponse,
    responses={400: {"model": ErrorResponse}},
    status_code=201,
)
def ingest_observation(observation: dict):
    trace_id = _trace_id()

    payload = observation

# Detect Group 3 V2.1 payload shape.
    is_v21 = (
        "quality_state" in payload
        and "calibration_state" in payload
        and isinstance(payload.get("location"), dict)
        and isinstance(payload.get("measurement"), dict)
    )

    if is_v21:
    # Validate against the frozen Group 3 V2.1 contract.
        errors = validate_v21_observation(payload)

        if errors:
            return JSONResponse(
                status_code=400,
                content={
                "trace_id": trace_id,
                "status": "REJECTED",
                "message": "Observation failed Group 3 V2.1 contract validation.",
                "errors": errors,
                },
            )
        

    # Adapt V2.1 into the existing v0.4 canonical persistence shape.
        canonical_payload = adapt_v21_to_canonical(payload)

    else:
    # Preserve the existing contract/path.
        errors = validate_observation(payload)

    if errors:
        return JSONResponse(
            status_code=400,
            content={
                "trace_id": trace_id,
                "status": "REJECTED",
                "message": "Observation failed Group 3 contract validation.",
                "errors": errors,
            },
        )

    canonical_payload = payload

    result = persist_observation(
        canonical_payload,
        idempotency_key=payload.get("idempotency_key"),
    )

    status = result["status"]
    http_status = result["http_status"]

    if status == "ACCEPTED":
        return JSONResponse(
            status_code=http_status,
            content={
                "trace_id": trace_id,
                "observation_id": result["observation_id"],
                "status": "ACCEPTED",
                "message": "Observation persisted through canonical VANA persistence.",
            },
        )

    if status == "IDEMPOTENT_REPLAY":
        return JSONResponse(
            status_code=http_status,
            content={
                "trace_id": trace_id,
                "observation_id": result["observation_id"],
                "status": "IDEMPOTENT_REPLAY",
                "message": "Request already processed; returning the canonical result.",
            },
        )

    if status == "IDEMPOTENCY_CONFLICT":
        return JSONResponse(
            status_code=http_status,
            content={
                "trace_id": trace_id,
                "observation_id": result["observation_id"],
                "status": "IDEMPOTENCY_CONFLICT",
                "message": "Idempotency-Key was already used with a different request payload.",
                "errors": [],
            },
        )

    if status == "DUPLICATE":
        return JSONResponse(
            status_code=http_status,
            content={
                "trace_id": trace_id,
                "observation_id": result["observation_id"],
                "status": "DUPLICATE",
                "message": "Observation already exists.",
                "errors": [],
            },
        )

    return JSONResponse(
        status_code=500,
        content={
            "trace_id": trace_id,
            "status": "ERROR",
            "message": "Unexpected persistence result.",
            "errors": [],
        },
    )


@app.get(
    "/observations/{observation_id}",
    response_model=RetrievalResponse,
    responses={404: {"model": ErrorResponse}},
)
def retrieve_observation(observation_id: str):
    trace_id = _trace_id()

    observation = retrieve_persisted_observation(observation_id)

    if observation is None:
        return JSONResponse(
            status_code=404,
            content={
                "trace_id": trace_id,
                "status": "NOT_FOUND",
                "message": "Observation was not found.",
                "errors": [],
            },
        )

    return RetrievalResponse(
        trace_id=trace_id,
        observation_id=observation_id,
        status="RETRIEVED",
        observation=observation,
    )
