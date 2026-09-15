"""Strict transient response models for the read-only operator API."""

from __future__ import annotations

from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv4Interface
from pathlib import PurePosixPath
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_serializer, field_validator

SafeText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Status = Literal["healthy", "degraded", "unavailable", "unknown"]
Source = Literal["nautobot", "kafka", "temporal", "worker", "consumer", "artifact", "device"]
AvailabilityCode = Literal[
    "ok", "timeout", "unreachable", "invalid_response", "not_configured", "not_found",
    "no_pollers", "no_members", "history_unavailable", "artifact_missing", "unknown",
]


class ReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UtcModel(ReadModel):
    @field_validator("*", mode="after")
    @classmethod
    def require_utc(cls, value: object) -> object:
        if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_values(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat().replace("+00:00", "Z")
        return value


class SourceAvailability(UtcModel):
    source: Source
    status: Status
    observed_at: datetime
    duration_ms: int | None = Field(default=None, ge=0, le=120_000)
    code: AvailabilityCode | None = None
    message: SafeText | None = None


T = TypeVar("T")


class AvailabilityEnvelope(UtcModel, Generic[T]):
    availability: SourceAvailability
    data: T | None


class ApiError(ReadModel):
    code: Literal["invalid_request", "not_found", "upstream_timeout", "temporarily_unavailable", "internal_error"]
    message: SafeText
    request_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class SystemHealthSummary(UtcModel):
    overall_status: Literal["healthy", "degraded", "unavailable"]
    observed_at: datetime
    nautobot: SourceAvailability
    kafka: SourceAvailability
    temporal: SourceAvailability
    worker: SourceAvailability
    consumer: SourceAvailability
    device_validation: SourceAvailability


class ArtifactSummary(ReadModel):
    relative_path: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] | None = None
    byte_count: int | None = Field(default=None, ge=0, le=1_048_576)
    available: bool

    @field_validator("relative_path")
    @classmethod
    def require_confined_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            "\\" in value
            or path.is_absolute()
            or not path.parts
            or value != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("artifact path must be normalized and relative")
        return value


class ValidationSummary(UtcModel):
    status: Literal["passed", "failed", "unavailable", "unknown"]
    validated_at: datetime | None = None
    checks_total: int | None = Field(default=None, ge=0, le=64)
    checks_failed: int | None = Field(default=None, ge=0, le=64)


class DeploymentSummary(UtcModel):
    workflow_id: Name
    run_id: UUID
    device_name: Name | None = None
    status: Literal["queued", "preparing", "deploying", "validating", "succeeded", "failed", "unknown"]
    artifact: ArtifactSummary | None = None
    deployed_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    validation_status: Literal["passed", "failed", "unavailable", "unknown"]
    failure_stage: Literal["prepare", "deploy", "validate", "publish", "execution"] | None = None
    failure_category: SafeText | None = None


class DeviceSummary(UtcModel):
    name: Name
    role: Name | None = None
    platform: Name | None = None
    location: Name | None = None
    management_address: IPv4Address | None = None
    inventory_status: Name | None = None
    last_deployment: DeploymentSummary | None = None
    validation_status: Literal["passed", "failed", "unavailable", "unknown"] = "unavailable"
    observed_at: datetime


class IntendedInterface(ReadModel):
    name: Name
    description: SafeText | None = None
    ipv4: IPv4Interface


class IntendedBgpNeighbor(ReadModel):
    address: IPv4Address
    remote_asn: int = Field(ge=1, le=4_294_967_295)
    description: SafeText | None = None


class IntendedStateSummary(ReadModel):
    hostname: Name
    loopback: IPv4Interface | None
    routed_interfaces: tuple[IntendedInterface, ...]
    bgp_local_asn: int | None = Field(default=None, ge=1, le=4_294_967_295)
    bgp_neighbors: tuple[IntendedBgpNeighbor, ...]


class SafeValidationCheck(ReadModel):
    name: Name
    status: Literal["passed", "failed"]
    expected: str | int | bool
    observed: str | int | bool | None
    message: SafeText | None = None


class LiveStateSummary(UtcModel):
    status: Literal["passed", "failed", "unavailable"]
    hostname: SafeValidationCheck | None = None
    interfaces: tuple[SafeValidationCheck, ...] = ()
    bgp: tuple[SafeValidationCheck, ...] = ()
    mismatch_count: int = Field(ge=0, le=64)
    validated_at: datetime | None = None


class DeviceDetail(ReadModel):
    summary: DeviceSummary
    intent: AvailabilityEnvelope[IntendedStateSummary]
    latest_artifact: AvailabilityEnvelope[ArtifactSummary]
    latest_deployment: AvailabilityEnvelope[DeploymentSummary]
    historical_validation: AvailabilityEnvelope[ValidationSummary]
    live_state: AvailabilityEnvelope[LiveStateSummary]


class WorkflowSummary(UtcModel):
    workflow_id: Name
    run_id: UUID
    kind: Literal["render", "deployment"]
    event_id: UUID | None = None
    correlation_id: UUID | None = None
    device_name: Name | None = None
    execution_status: Literal["running", "completed", "failed", "canceled", "terminated", "timed_out", "continued_as_new", "unknown"]
    outcome: Literal["running", "render_succeeded", "render_failed", "deployment_succeeded", "deployment_failed", "execution_failed", "execution_canceled", "execution_terminated", "execution_timed_out", "continued_as_new", "unknown"]
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    current_stage: Name | None = None
    failure_category: SafeText | None = None
    data_status: Literal["complete", "partial", "unavailable"]


class ExecutionStage(UtcModel):
    sequence: int = Field(ge=1, le=64)
    key: Name
    label: SafeText
    status: Literal["completed", "running", "failed", "not_reached", "unknown"]
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    attempts: int | None = Field(default=None, ge=1, le=100)
    failure_category: SafeText | None = None
    failure_message: SafeText | None = None


class SafeFailureSummary(ReadModel):
    stage: Name | None = None
    category: SafeText
    message: SafeText


class WorkflowDetail(ReadModel):
    summary: WorkflowSummary
    stages: tuple[ExecutionStage, ...] = Field(max_length=64)
    artifact: ArtifactSummary | None = None
    deployment: DeploymentSummary | None = None
    validation: ValidationSummary | None = None
    failure: SafeFailureSummary | None = None
    history_status: SourceAvailability


class TopologyNode(ReadModel):
    id: Name
    label: Name
    role: Name | None = None
    platform: Name | None = None
    status: Literal["healthy", "degraded", "failed", "unknown"] = "unknown"
    status_source: Literal["inventory", "deployment", "validation"] | None = None


class TopologyLink(ReadModel):
    id: Name
    kind: Literal["physical", "bgp"]
    source_device: Name
    source_interface: Name | None = None
    target_device: Name
    target_interface: Name | None = None
    status: Literal["healthy", "degraded", "failed", "unknown"] = "unknown"


class TopologyGraph(UtcModel):
    nodes: tuple[TopologyNode, ...] = Field(max_length=100)
    links: tuple[TopologyLink, ...] = Field(max_length=200)
    observed_at: datetime
    availability: SourceAvailability


class DeviceList(UtcModel):
    items: tuple[DeviceSummary, ...]
    count: int = Field(ge=0, le=100)
    observed_at: datetime
    availability: SourceAvailability


class WorkflowList(UtcModel):
    items: tuple[WorkflowSummary, ...]
    count: int = Field(ge=0, le=50)
    observed_at: datetime
    availability: SourceAvailability


class DeploymentList(UtcModel):
    items: tuple[DeploymentSummary, ...]
    count: int = Field(ge=0, le=50)
    observed_at: datetime
    availability: SourceAvailability


class CountSection(ReadModel):
    availability: SourceAvailability
    total: int | None = Field(default=None, ge=0, le=100)


class WorkflowOverview(ReadModel):
    availability: SourceAvailability
    active_count: int | None = Field(default=None, ge=0, le=50)
    recent: tuple[WorkflowSummary, ...] = Field(max_length=8)


class DeploymentOverview(ReadModel):
    availability: SourceAvailability
    recent_successes: tuple[DeploymentSummary, ...] = Field(max_length=8)
    recent_failures: tuple[DeploymentSummary, ...] = Field(max_length=8)


class TopologyOverview(ReadModel):
    availability: SourceAvailability
    nodes: tuple[TopologyNode, ...] = Field(max_length=100)
    links: tuple[TopologyLink, ...] = Field(max_length=200)


class ActivitySection(ReadModel):
    availability: SourceAvailability
    items: tuple[WorkflowSummary, ...] = Field(max_length=8)


class Overview(UtcModel):
    observed_at: datetime
    health: SystemHealthSummary
    devices: CountSection
    workflows: WorkflowOverview
    deployments: DeploymentOverview
    topology: TopologyOverview
    activity: ActivitySection
