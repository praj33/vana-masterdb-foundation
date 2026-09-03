from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

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
from api.models import OfficialForestCoverRequest
from api.official_forest_cover import (
    list_official_forest_cover,
    persist_official_forest_cover,
    retrieve_official_forest_cover,
    validate_official_record,
)


app = FastAPI(
    title="VANA MasterDB Observation API",
    version="1.0.0",
    description="Consumer-facing Group 3 observation ingestion and retrieval API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.post("/official/forest-cover", status_code=201)
def ingest_official_forest_cover(
    request: OfficialForestCoverRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    payload = request.model_dump()
    errors = validate_official_record(payload)
    if errors:
        raise HTTPException(status_code=400, detail=errors)
    result = persist_official_forest_cover(payload, idempotency_key=idempotency_key)
    return JSONResponse(status_code=result["http_status"], content=result)


@app.get("/official/forest-cover/{record_id}")
def get_official_forest_cover(record_id: str):
    record = retrieve_official_forest_cover(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Official forest-cover record was not found")
    return record


@app.get("/datasets/{dataset_id}/forest-cover")
def get_dataset_forest_cover(dataset_id: str):
    return {"dataset_id": dataset_id, "records": list_official_forest_cover(dataset_id)}


@app.post(
    "/observations",
    response_model=IngestionResponse,
    responses={400: {"model": ErrorResponse}},
    status_code=201,
)
def ingest_observation(
    observation: dict,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    trace_id = _trace_id()

    payload = observation

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

    key = idempotency_key or payload.get("idempotency_key")

    result = persist_observation(
        payload,
        idempotency_key=key,
    )


    status = result["status"]
    http_status = result["http_status"]

    if status == "ACCEPTED":
        return JSONResponse(
            status_code=http_status,
            content={
                "trace_id": trace_id,
                "observation_id": result["observation_id"],
                "canonical_record_id": result.get("canonical_record_id"),
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
                "canonical_record_id": result.get("canonical_record_id"),
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
                "canonical_record_id": None,
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
                "canonical_record_id": result.get("canonical_record_id"),
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
