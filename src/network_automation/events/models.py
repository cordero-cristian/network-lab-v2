"""Strict event and Temporal payload models for automation execution."""

from __future__ import annotations

from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv4Interface
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
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
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ArtifactBytes = Annotated[int, Field(strict=True, ge=1, le=1024 * 1024)]
Port = Annotated[int, Field(strict=True, ge=1, le=65535)]
Asn = Annotated[int, Field(strict=True, ge=1, le=4294967295)]
BoundedName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
SafeScalarText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
SafeScalar = (
    SafeScalarText
    | Annotated[int, Field(strict=True)]
    | Annotated[bool, Field(strict=True)]
)
DeploymentFailureType = Literal[
    "nautobot_unavailable",
    "nautobot_rejected",
    "intent_invalid",
    "unsupported_platform",
    "management_address_invalid",
    "artifact_unavailable",
    "artifact_invalid",
    "artifact_mismatch",
    "device_settings_missing",
    "device_unavailable",
    "device_authentication_failed",
    "device_identity_mismatch",
    "device_platform_mismatch",
    "configuration_rejected",
    "device_state_invalid",
    "validation_not_converged",
    "validation_failed",
    "internal_error",
]

_PREPARE_FAILURE_TYPES = {
    "nautobot_unavailable",
    "nautobot_rejected",
    "intent_invalid",
    "unsupported_platform",
    "management_address_invalid",
    "artifact_unavailable",
    "artifact_invalid",
    "artifact_mismatch",
    "device_settings_missing",
}
_DEPLOY_FAILURE_TYPES = {
    "device_unavailable",
    "device_authentication_failed",
    "device_identity_mismatch",
    "device_platform_mismatch",
    "configuration_rejected",
    "artifact_mismatch",
    "internal_error",
}
_VALIDATE_FAILURE_TYPES = {
    "device_unavailable",
    "device_authentication_failed",
    "device_state_invalid",
    "validation_not_converged",
    "validation_failed",
    "internal_error",
}


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value


def _serialize_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> object:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


def _parse_uuid(value: object) -> object:
    if isinstance(value, str):
        try:
            parsed = UUID(value)
        except ValueError:
            return value
        return parsed if str(parsed) == value else value
    return value


def _parse_ipv4_address(value: object, info: ValidationInfo) -> object:
    if info.mode == "json":
        return value
    if isinstance(value, str):
        try:
            return IPv4Address(value)
        except ValueError:
            return value
    return value


def _parse_ipv4_interface(value: object, info: ValidationInfo) -> object:
    if info.mode == "json":
        return value
    if isinstance(value, str):
        try:
            return IPv4Interface(value)
        except ValueError:
            return value
    return value


StrictUuid = Annotated[UUID, BeforeValidator(_parse_uuid)]
UtcTimestamp = Annotated[datetime, BeforeValidator(_parse_datetime)]
StrictIPv4Address = Annotated[IPv4Address, BeforeValidator(_parse_ipv4_address)]
StrictIPv4Interface = Annotated[IPv4Interface, BeforeValidator(_parse_ipv4_interface)]


def _require_optional_utc(value: datetime | None) -> datetime | None:
    return _require_utc(value) if value is not None else None


def _require_safe_text(value: str) -> str:
    if not value.isprintable():
        raise ValueError("safe text must contain only printable characters")
    return value


def _require_deployment_workflow_id(value: str) -> str:
    prefix = "deploy-device-config:"
    if not value.startswith(prefix):
        raise ValueError("workflow ID must identify a deployment workflow")
    event_id = value.removeprefix(prefix)
    try:
        parsed = UUID(event_id)
    except ValueError as error:
        raise ValueError("workflow ID must contain a canonical UUID") from error
    if str(parsed) != event_id:
        raise ValueError("workflow ID must contain a canonical UUID")
    return value


class DeploymentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


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


class DeploymentRequested(DeploymentModel):
    event_type: Literal["network.deployment.requested"]
    event_version: Literal[1]
    event_id: StrictUuid
    correlation_id: StrictUuid
    device_name: DeviceName
    requested_at: UtcTimestamp
    source: SourceText

    _validate_requested_at = field_validator("requested_at")(_require_utc)
    _serialize_requested_at = field_serializer("requested_at")(_serialize_utc)


class DeploymentCompleted(DeploymentModel):
    event_type: Literal["network.deployment.completed"]
    event_version: Literal[1]
    event_id: StrictUuid
    correlation_id: StrictUuid
    device_name: DeviceName
    workflow_id: WorkflowId
    artifact_path: str
    artifact_sha256: Sha256
    artifact_bytes: ArtifactBytes
    deployed_at: UtcTimestamp
    validation_status: Literal["passed"]
    completed_at: UtcTimestamp

    _validate_deployed_at = field_validator("deployed_at")(_require_utc)
    _validate_completed_at = field_validator("completed_at")(_require_utc)
    _serialize_deployed_at = field_serializer("deployed_at")(_serialize_utc)
    _serialize_completed_at = field_serializer("completed_at")(_serialize_utc)
    _validate_workflow_id = field_validator("workflow_id")(_require_deployment_workflow_id)

    @model_validator(mode="after")
    def require_consistent_completion(self) -> Self:
        if self.artifact_path != str(
            PurePosixPath("artifacts/configs") / f"{self.device_name}.cfg"
        ):
            raise ValueError("artifact path must match the event device")
        if self.completed_at < self.deployed_at:
            raise ValueError("completion cannot precede deployment")
        return self


class DeploymentFailed(DeploymentModel):
    event_type: Literal["network.deployment.failed"]
    event_version: Literal[1]
    event_id: StrictUuid
    correlation_id: StrictUuid
    device_name: DeviceName
    workflow_id: WorkflowId
    failure_stage: Literal["prepare", "deploy", "validate"]
    error_type: DeploymentFailureType
    error_message: ErrorMessage
    failed_at: UtcTimestamp
    artifact_sha256: Sha256 | None
    artifact_bytes: ArtifactBytes | None
    deployed_at: UtcTimestamp | None

    _validate_failed_at = field_validator("failed_at")(_require_utc)
    _validate_deployed_at = field_validator("deployed_at")(_require_optional_utc)
    _serialize_failed_at = field_serializer("failed_at")(_serialize_utc)
    _serialize_deployed_at = field_serializer("deployed_at")(
        lambda value: _serialize_utc(value) if value is not None else None
    )
    _validate_workflow_id = field_validator("workflow_id")(_require_deployment_workflow_id)
    _validate_error_message = field_validator("error_message")(_require_safe_text)

    @model_validator(mode="after")
    def require_stage_metadata(self) -> Self:
        allowed_types = {
            "prepare": _PREPARE_FAILURE_TYPES,
            "deploy": _DEPLOY_FAILURE_TYPES,
            "validate": _VALIDATE_FAILURE_TYPES,
        }[self.failure_stage]
        if self.error_type not in allowed_types:
            raise ValueError("failure category does not belong to its stage")

        if self.failure_stage == "prepare":
            if any(
                value is not None
                for value in (self.artifact_sha256, self.artifact_bytes, self.deployed_at)
            ):
                raise ValueError("prepare failure cannot contain deployment metadata")
        elif self.failure_stage == "deploy":
            if self.artifact_sha256 is None or self.artifact_bytes is None:
                raise ValueError("deploy failure requires artifact metadata")
            if self.deployed_at is not None:
                raise ValueError("deploy failure cannot contain a deployment timestamp")
        elif any(
            value is None
            for value in (self.artifact_sha256, self.artifact_bytes, self.deployed_at)
        ):
            raise ValueError("validation failure requires deployment metadata")

        if self.deployed_at is not None and self.failed_at < self.deployed_at:
            raise ValueError("failure cannot precede deployment")
        return self


class DeployDeviceConfigRequest(DeploymentModel):
    operation: Literal["deploy"]
    event_id: StrictUuid
    correlation_id: StrictUuid
    device_name: DeviceName


class ArtifactIdentity(DeploymentModel):
    device_name: DeviceName
    artifact_path: str
    sha256: Sha256
    byte_count: ArtifactBytes

    @model_validator(mode="after")
    def require_artifact_path(self) -> Self:
        if self.artifact_path != str(
            PurePosixPath("artifacts/configs") / f"{self.device_name}.cfg"
        ):
            raise ValueError("artifact path must match the identity device")
        return self


class DeploymentTarget(DeploymentModel):
    device_name: DeviceName
    management_address: StrictIPv4Address
    platform: Literal["nokia_srl"]
    gnmi_port: Port
    tls_mode: Literal["insecure"]


class ExpectedInterface(DeploymentModel):
    name: BoundedName
    ipv4_prefix: StrictIPv4Interface
    require_oper_up: bool


class ExpectedBgpNeighbor(DeploymentModel):
    address: StrictIPv4Address
    remote_asn: Asn


class ExpectedDeviceState(DeploymentModel):
    device_name: DeviceName
    loopback_name: BoundedName
    loopback_prefix: StrictIPv4Interface
    routed_interfaces: tuple[ExpectedInterface, ...] = Field(min_length=1, max_length=64)
    local_asn: Asn
    bgp_neighbors: tuple[ExpectedBgpNeighbor, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def require_valid_expected_state(self) -> Self:
        if self.loopback_prefix.network.prefixlen != 32:
            raise ValueError("loopback prefix must use /32")
        interface_names = [interface.name for interface in self.routed_interfaces]
        if len(interface_names) != len(set(interface_names)):
            raise ValueError("routed interface names must be unique")
        neighbor_addresses = [neighbor.address for neighbor in self.bgp_neighbors]
        if len(neighbor_addresses) != len(set(neighbor_addresses)):
            raise ValueError("BGP neighbor addresses must be unique")
        check_count = (
            7
            + sum(5 if interface.require_oper_up else 3 for interface in self.routed_interfaces)
            + 2 * len(self.bgp_neighbors)
        )
        if check_count > 64:
            raise ValueError("expected state exceeds the validation check bound")
        return self


class PreparedDeployment(DeploymentModel):
    artifact: ArtifactIdentity
    target: DeploymentTarget
    expected_state: ExpectedDeviceState

    @model_validator(mode="after")
    def require_matching_devices(self) -> Self:
        devices = {
            self.artifact.device_name,
            self.target.device_name,
            self.expected_state.device_name,
        }
        if len(devices) != 1:
            raise ValueError("prepared deployment devices must match")
        return self


class DeploymentResult(DeploymentModel):
    artifact: ArtifactIdentity
    device_name: DeviceName
    management_address: StrictIPv4Address
    deployed_at: UtcTimestamp

    _validate_deployed_at = field_validator("deployed_at")(_require_utc)
    _serialize_deployed_at = field_serializer("deployed_at")(_serialize_utc)

    @model_validator(mode="after")
    def require_matching_device(self) -> Self:
        if self.artifact.device_name != self.device_name:
            raise ValueError("deployment result device must match artifact identity")
        return self


class ValidationCheck(DeploymentModel):
    name: BoundedName
    status: Literal["passed", "failed"]
    expected: SafeScalar
    observed: SafeScalar | None
    message: ErrorMessage | None

    _validate_name = field_validator("name")(_require_safe_text)
    _validate_expected = field_validator("expected")(
        lambda value: _require_safe_text(value) if isinstance(value, str) else value
    )
    _validate_observed = field_validator("observed")(
        lambda value: _require_safe_text(value) if isinstance(value, str) else value
    )
    _validate_message = field_validator("message")(
        lambda value: _require_safe_text(value) if value is not None else None
    )


class DeviceValidationResult(DeploymentModel):
    device_name: DeviceName
    status: Literal["passed", "failed"]
    checks: tuple[ValidationCheck, ...] = Field(min_length=1, max_length=64)
    validated_at: UtcTimestamp

    _validate_validated_at = field_validator("validated_at")(_require_utc)
    _serialize_validated_at = field_serializer("validated_at")(_serialize_utc)

    @model_validator(mode="after")
    def require_consistent_status(self) -> Self:
        names = [check.name for check in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("validation check names must be unique")
        expected_status = (
            "passed" if all(check.status == "passed" for check in self.checks) else "failed"
        )
        if self.status != expected_status:
            raise ValueError("validation result status must match its checks")
        return self


def workflow_id_for(event_id: UUID) -> str:
    return f"render-device-config:{event_id}"


def deployment_workflow_id_for(event_id: UUID) -> str:
    return f"deploy-device-config:{event_id}"
