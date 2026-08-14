from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.models import ErrorResponse, IngestionResponse, ObservationRequest, RetrievalResponse
from api.validation import validate_observation


app = FastAPI(
    title="VANA MasterDB Observation API",
    version="1.0.0",
    description="Consumer-facing Group 1 observation ingestion and retrieval API.",
)


# Temporary adapter for API-contract testing.
# This will be replaced by the canonical MasterDB persistence adapter
# once the approved schema boundary is available.
_observation_store: dict[str, dict] = {}


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

    observation_id = payload["observation_id"]

    if observation_id in _observation_store:
        return JSONResponse(
            status_code=409,
            content={
                "trace_id": trace_id,
                "status": "DUPLICATE",
                "message": "Observation already exists.",
                "errors": [],
            },
        )

    _observation_store[observation_id] = payload

    return IngestionResponse(
        trace_id=trace_id,
        observation_id=observation_id,
        status="ACCEPTED",
        message="Observation accepted for canonical persistence.",
    )


@app.get(
    "/observations/{observation_id}",
    response_model=RetrievalResponse,
    responses={404: {"model": ErrorResponse}},
)
def retrieve_observation(observation_id: str):
    trace_id = _trace_id()

    observation = _observation_store.get(observation_id)

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
