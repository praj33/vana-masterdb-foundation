from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ObservationRequest(BaseModel):
    """
    Consumer-facing Group 3 observation payload.

    Contract validation remains authoritative in api.validation.
    """

    model_config = ConfigDict(extra="allow")

    observation_id: str
    device_id: str
    timestamp: str

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    observation_type: str
    measurement: Any
    unit: Optional[str] = None

    accuracy: str
    calibration_status: str
    raw_artifact_reference: Dict[str, Any]

    quality_status: str
    processing_status: str
    provenance: Dict[str, Any]

    idempotency_key: Optional[str] = None


class IngestionResponse(BaseModel):
    trace_id: str
    observation_id: str
    status: str
    message: str


class RetrievalResponse(BaseModel):
    trace_id: str
    observation_id: str
    status: str
    observation: Dict[str, Any]


class ErrorResponse(BaseModel):
    trace_id: str
    status: str
    message: str
    errors: List[str]
