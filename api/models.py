from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


class ObservationRequest(BaseModel):
    """
    Consumer-facing Group 3 V2.2 observation payload.

    Contract validation remains authoritative in api.validation.
    """

    model_config = ConfigDict(extra="allow")

    observation_id: str
    device_id: Optional[str] = None
    timestamp: Optional[str] = None
    observation_timestamp: Optional[str] = None

    contract_version: Optional[str] = None
    source_identity: Optional[str] = None
    survey_id: Optional[str] = None
    zone_id: Optional[str] = None
    flight_id: Optional[str] = None
    sensor_id: Optional[str] = None
    observation_seq: Optional[str] = None
    mission_id: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    elevation: Optional[float] = None

    location: Optional[Dict[str, Any]] = None

    synthetic_state: Optional[str] = None
    is_synthetic: Optional[bool] = None
    capture_method: Optional[str] = None
    observation_type: Optional[str] = None
    measurement: Any = None
    parameter: Optional[str] = None
    unit: Optional[str] = None

    accuracy: Optional[Union[float, str]] = "NOT_VERIFIED"
    calibration_status: Optional[str] = None
    calibration_state: Optional[str] = None
    quality_status: Optional[str] = None
    quality_state: Optional[str] = None
    data_state: Optional[str] = None

    gnss_status: Optional[str] = None
    position_accuracy_m: Optional[float] = None

    raw_artifact: Optional[str] = None
    raw_artifact_integrity: Optional[Dict[str, Any]] = None
    raw_artifact_reference: Optional[Dict[str, Any]] = None
    provenance_reference: Optional[str] = None
    processing_status: Optional[str] = None
    provenance: Optional[Dict[str, Any]] = None

    tidal_state: Optional[Any] = None
    idempotency_key: Optional[str] = None


class IngestionResponse(BaseModel):
    trace_id: str
    observation_id: str
    canonical_record_id: Optional[str] = None
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
