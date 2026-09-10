"""Strict event and Temporal payload models for render execution."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

from network_automation.intent.models import DeviceName

SourceText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
WorkflowId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ErrorMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
ErrorType = Literal[
    "nautobot_unavailable",
    "artifact_unavailable",
    "intent_invalid",
    "nautobot_rejected",
    "unsupported_platform",
    "render_invalid",
    "internal_error",
]


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value


def _serialize_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class RenderRequested(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: Literal["network.render.requested"]
    event_version: Literal[1]
    event_id: UUID
    correlation_id: UUID
    device_name: DeviceName
    requested_at: datetime
    source: SourceText

    _validate_requested_at = field_validator("requested_at")(_require_utc)
    _serialize_requested_at = field_serializer("requested_at")(_serialize_utc)


class RenderCompleted(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: Literal["network.render.completed"]
    event_version: Literal[1]
    event_id: UUID
    correlation_id: UUID
    device_name: DeviceName
    workflow_id: WorkflowId
    artifact_path: str
    completed_at: datetime

    _validate_completed_at = field_validator("completed_at")(_require_utc)
    _serialize_completed_at = field_serializer("completed_at")(_serialize_utc)

    @model_validator(mode="after")
    def require_artifact_path(self) -> Self:
        if self.artifact_path != str(PurePosixPath("artifacts/configs") / f"{self.device_name}.cfg"):
            raise ValueError("artifact path must match the event device")
        return self


class RenderFailed(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: Literal["network.render.failed"]
    event_version: Literal[1]
    event_id: UUID
    correlation_id: UUID
    device_name: DeviceName
    workflow_id: WorkflowId
    error_type: ErrorType
    error_message: ErrorMessage
    failed_at: datetime

    _validate_failed_at = field_validator("failed_at")(_require_utc)
    _serialize_failed_at = field_serializer("failed_at")(_serialize_utc)


class RenderDeviceConfigRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    correlation_id: UUID
    device_name: DeviceName


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    device_name: DeviceName
    artifact_path: str

    @model_validator(mode="after")
    def require_artifact_path(self) -> Self:
        if self.artifact_path != str(PurePosixPath("artifacts/configs") / f"{self.device_name}.cfg"):
            raise ValueError("artifact path must match the metadata device")
        return self


def workflow_id_for(event_id: UUID) -> str:
    return f"render-device-config:{event_id}"
