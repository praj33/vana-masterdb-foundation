from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


class ObservationRequest(BaseModel):
    """
    Consumer-facing Group 3 V2.1 observation payload.

    Contract validation remains authoritative in api.validation.
    """

    model_config = ConfigDict(extra="allow")

    observation_id: str
    device_id: str
    timestamp: str

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    elevation: Optional[float] = None

    location: Optional[Dict[str, Any]] = None

    is_synthetic: Optional[bool] = None
    capture_method: Optional[str] = None
    observation_type: Optional[str] = None
    measurement: Any = None
    parameter: Optional[str] = None
    unit: Optional[str] = None

    accuracy: Optional[Union[float, str]] = "NOT VERIFIED"
    calibration_status: Optional[str] = None
    calibration_state: Optional[str] = None
    quality_status: Optional[str] = None
    quality_state: Optional[str] = None

    gnss_status: Optional[str] = None
    position_accuracy_m: Optional[float] = None

    raw_artifact_reference: Dict[str, Any]
    processing_status: str
    provenance: Dict[str, Any]

    tidal_state: Optional[str] = None
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
