"""Bounded Temporal visibility and history projections."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHistoryEventFilterType
from temporalio.service import RPCError, RPCStatusCode

from network_automation.api.models import (
    ArtifactSummary,
    DeploymentList,
    DeploymentSummary,
    ExecutionStage,
    SafeFailureSummary,
    SourceAvailability,
    ValidationSummary,
    WorkflowDetail,
    WorkflowList,
    WorkflowSummary,
)
from network_automation.events.models import (
    DeploymentCompleted,
    DeploymentFailed,
    DeploymentResult,
    DeployDeviceConfigRequest,
    DeviceValidationResult,
    PreparedDeployment,
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
)

WORKFLOW_ID = re.compile(r"^(render-device-config|deploy-device-config):([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$")
VISIBILITY_QUERY = 'WorkflowType = "RenderDeviceConfigWorkflow"'
ACTIVITY_STAGES = {
    "prepare_device_deployment": ("prepare", "Intent prepared and artifact written"),
    "render_device_artifact": ("render", "Intent rendered and artifact written"),
    "deploy_device_artifact": ("deploy", "gNMI deployment"),
    "validate_device_state": ("validate", "Operational validation"),
    "publish_render_result": ("publish", "Result published"),
}
SAFE_FAILURE_MESSAGES = {
    "nautobot_unavailable": "Nautobot is temporarily unavailable",
    "device_unavailable": "Device state is temporarily unavailable",
    "device_authentication_failed": "Device authentication failed",
    "validation_failed": "Device state did not match intended invariants",
    "validation_not_converged": "Device state has not converged",
    "internal_error": "Automation execution failed",
    "execution_failed": "Workflow execution failed",
    "execution_canceled": "Workflow execution was canceled",
    "execution_terminated": "Workflow execution was terminated",
    "execution_timed_out": "Workflow execution timed out",
}


def validate_workflow_id(value: str, *, deployment_only: bool = False) -> str:
    match = WORKFLOW_ID.fullmatch(value)
    if match is None or (deployment_only and match.group(1) != "deploy-device-config"):
        raise ValueError("invalid workflow ID")
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _available(source: str = "temporal") -> SourceAvailability:
    return SourceAvailability(source=source, status="healthy", observed_at=_now(), code="ok")


def _unavailable(code: str = "unreachable") -> SourceAvailability:
    return SourceAvailability(
        source="temporal", status="unavailable", observed_at=_now(), code=code,
        message="Temporal workflow data is unavailable",
    )


def _history_unavailable() -> SourceAvailability:
    return SourceAvailability(
        source="temporal", status="degraded", observed_at=_now(),
        code="history_unavailable", message="Workflow history is unavailable",
    )


def _execution_status(value: object) -> str:
    name = getattr(value, "name", str(value)).lower()
    for status in ("continued_as_new", "timed_out", "terminated", "canceled", "completed", "failed", "running"):
        if status in name:
            return status
    return "unknown"


def _kind(workflow_id: str) -> str:
    return "deployment" if workflow_id.startswith("deploy-device-config:") else "render"


async def _decode_payloads(client: Any, payloads: Any, model_types: tuple[type, ...]) -> Any | None:
    values = getattr(payloads, "payloads", payloads)
    if not values:
        return None
    for model_type in model_types:
        try:
            decoded = await client.data_converter.decode(values, [model_type])
            if decoded:
                return decoded[0]
        except Exception:
            continue
    return None


async def _history(client: Any, workflow_id: str, run_id: str) -> list[Any]:
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    events: list[Any] = []
    async for event in handle.fetch_history_events(page_size=256):
        events.append(event)
    return events


async def _hydrate(client: Any, execution: Any, *, all_events: bool = False) -> tuple[Any | None, Any | None, list[Any]]:
    if all_events:
        events = await _history(client, execution.id, execution.run_id)
    else:
        handle = client.get_workflow_handle(execution.id, run_id=execution.run_id)
        events = []
        async for event in handle.fetch_history_events(page_size=1):
            events.append(event)
            break
        async for event in handle.fetch_history_events(
            page_size=1,
            event_filter_type=WorkflowHistoryEventFilterType.CLOSE_EVENT,
        ):
            if not events or event.event_id != events[0].event_id:
                events.append(event)
            break
    request = result = None
    for event in events:
        event_name = _event_name(event)
        if event_name == "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED":
            request = await _decode_payloads(
                client, event.workflow_execution_started_event_attributes.input,
                (DeployDeviceConfigRequest, RenderDeviceConfigRequest),
            )
        elif event_name == "EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED":
            result = await _decode_payloads(
                client, event.workflow_execution_completed_event_attributes.result,
                (DeploymentCompleted, DeploymentFailed, RenderCompleted, RenderFailed),
            )
    request, result = _correlate_payloads(execution, request, result)
    return request, result, events


def _correlate_payloads(
    execution: Any, request: Any | None, result: Any | None
) -> tuple[Any | None, Any | None]:
    match = WORKFLOW_ID.fullmatch(execution.id)
    if match is None:
        return None, None
    expected_event_id = UUID(match.group(2))
    request_type = (
        DeployDeviceConfigRequest
        if match.group(1) == "deploy-device-config"
        else RenderDeviceConfigRequest
    )
    result_types = (
        (DeploymentCompleted, DeploymentFailed)
        if match.group(1) == "deploy-device-config"
        else (RenderCompleted, RenderFailed)
    )
    if request is not None and (
        not isinstance(request, request_type)
        or request.event_id != expected_event_id
    ):
        return None, None
    if result is not None and (
        not isinstance(result, result_types)
        or result.workflow_id != execution.id
    ):
        result = None
    if request is not None and result is not None and (
        result.device_name != request.device_name
        or result.correlation_id != request.correlation_id
    ):
        result = None
    return request, result


def _artifact(result: Any, root: Path) -> ArtifactSummary | None:
    path_text = getattr(result, "artifact_path", None)
    if not isinstance(path_text, str):
        return None
    digest = getattr(result, "artifact_sha256", getattr(result, "sha256", None))
    byte_count = getattr(result, "artifact_bytes", getattr(result, "byte_count", None))
    root = root.resolve()
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return None
    return ArtifactSummary(
        relative_path=relative.as_posix(), sha256=digest, byte_count=byte_count,
        available=candidate.is_file(),
    )


def _summary(execution: Any, request: Any | None, result: Any | None) -> WorkflowSummary:
    execution_status = _execution_status(execution.status)
    outcome = "running" if execution_status == "running" else "unknown"
    failure_category = None
    if isinstance(result, DeploymentCompleted):
        outcome = "deployment_succeeded"
    elif isinstance(result, DeploymentFailed):
        outcome, failure_category = "deployment_failed", result.error_type
    elif isinstance(result, RenderCompleted):
        outcome = "render_succeeded"
    elif isinstance(result, RenderFailed):
        outcome, failure_category = "render_failed", result.error_type
    elif execution_status in {"failed", "canceled", "terminated", "timed_out", "continued_as_new"}:
        outcome = f"execution_{execution_status}" if execution_status != "continued_as_new" else execution_status
    completed_at = execution.close_time
    duration = None
    if completed_at is not None:
        duration = max(0, int((completed_at - execution.start_time).total_seconds() * 1000))
    return WorkflowSummary(
        workflow_id=execution.id,
        run_id=UUID(execution.run_id),
        kind=_kind(execution.id),
        event_id=getattr(request, "event_id", None),
        correlation_id=getattr(request, "correlation_id", None),
        device_name=getattr(request, "device_name", None),
        execution_status=execution_status,
        outcome=outcome,
        started_at=execution.start_time,
        completed_at=completed_at,
        duration_ms=duration,
        current_stage=getattr(result, "failure_stage", None),
        failure_category=failure_category,
        data_status="complete" if request is not None and (result is not None or execution_status == "running") else "partial",
    )


async def list_workflow_projections(
    client: Any,
    *,
    limit: int = 25,
    hydration_limit: int | None = None,
    hydration_concurrency: int = 4,
) -> tuple[WorkflowList, dict[tuple[str, UUID], Any]]:
    limit = max(1, min(limit, 50))
    executions = []
    async for execution in client.list_workflows(query=VISIBILITY_QUERY, limit=limit):
        if WORKFLOW_ID.fullmatch(execution.id) and execution.workflow_type == "RenderDeviceConfigWorkflow":
            executions.append(execution)
        if len(executions) >= limit:
            break
    executions.sort(key=lambda item: item.start_time, reverse=True)
    semaphore = asyncio.Semaphore(max(1, min(hydration_concurrency, 4)))

    async def one(execution: Any, hydrate: bool) -> tuple[WorkflowSummary, Any | None]:
        if not hydrate:
            return _summary(execution, None, None), None
        try:
            async with semaphore:
                request, result, _ = await _hydrate(client, execution)
        except (RPCError, TimeoutError):
            return _summary(execution, None, None), None
        return _summary(execution, request, result), result

    bound = len(executions) if hydration_limit is None else min(hydration_limit, 8)
    hydrated = await asyncio.gather(*(one(value, index < bound) for index, value in enumerate(executions)))
    items = tuple(item for item, _ in hydrated)
    results = {
        (item.workflow_id, item.run_id): result
        for item, result in hydrated if result is not None
    }
    return (
        WorkflowList(items=items, count=len(items), observed_at=_now(), availability=_available()),
        results,
    )


async def list_workflow_summaries(
    client: Any,
    *,
    limit: int = 25,
    hydration_limit: int | None = None,
    hydration_concurrency: int = 4,
) -> WorkflowList:
    workflows, _ = await list_workflow_projections(
        client,
        limit=limit,
        hydration_limit=hydration_limit,
        hydration_concurrency=hydration_concurrency,
    )
    return workflows


def deployment_from_summary(summary: WorkflowSummary, result: Any | None, artifact_root: Path) -> DeploymentSummary:
    status = "unknown"
    validation = "unknown"
    if summary.execution_status == "running":
        status = "queued"
    elif isinstance(result, DeploymentCompleted):
        status, validation = "succeeded", "passed"
    elif isinstance(result, DeploymentFailed):
        status = "failed"
        validation = "failed" if result.failure_stage == "validate" else "unavailable"
    elif summary.outcome == "deployment_succeeded":
        status, validation = "succeeded", "passed"
    elif summary.outcome == "deployment_failed":
        status = "failed"
        validation = "failed" if summary.current_stage == "validate" else "unavailable"
    elif summary.outcome in {
        "execution_failed", "execution_canceled", "execution_terminated", "execution_timed_out"
    }:
        status, validation = "failed", "unavailable"
    failure_stage = getattr(result, "failure_stage", None)
    if failure_stage is None and status == "failed" and summary.outcome.startswith("execution_"):
        failure_stage = "execution"
    return DeploymentSummary(
        workflow_id=summary.workflow_id, run_id=summary.run_id, device_name=summary.device_name,
        status=status, artifact=_artifact(result, artifact_root),
        deployed_at=getattr(result, "deployed_at", None), completed_at=summary.completed_at,
        duration_ms=summary.duration_ms, validation_status=validation,
        failure_stage=failure_stage,
        failure_category=(summary.failure_category or summary.outcome if status == "failed" else None),
    )


async def list_deployments(
    client: Any,
    *,
    limit: int,
    artifact_root: Path,
    hydration_concurrency: int = 4,
) -> DeploymentList:
    workflows, results = await list_workflow_projections(
        client, limit=limit, hydration_concurrency=hydration_concurrency
    )
    items = tuple(
        deployment_from_summary(item, results.get((item.workflow_id, item.run_id)), artifact_root)
        for item in workflows.items if item.kind == "deployment"
    )
    return DeploymentList(items=items, count=len(items), observed_at=workflows.observed_at, availability=workflows.availability)


def _safe_activity_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:96]
    return cleaned or "unknown"


def _event_time(event: Any) -> datetime:
    value = event.event_time.ToDatetime()
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _event_name(event: Any) -> str:
    try:
        return EventType.Name(event.event_type)
    except (TypeError, ValueError):
        return f"UNKNOWN_EVENT_{getattr(event, 'event_type', 'unknown')}"


def _pending_values(pending: tuple[Any, ...]) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for item in pending:
        activity_type = getattr(getattr(item, "activity_type", None), "name", None)
        if not isinstance(activity_type, str):
            continue
        attempt = getattr(item, "attempt", None)
        values[activity_type] = {
            "attempts": min(max(attempt, 1), 100) if isinstance(attempt, int) else None,
        }
    return values


def _stages(
    events: list[Any],
    *,
    execution_status: str,
    result: Any | None,
    pending: tuple[Any, ...] = (),
) -> tuple[ExecutionStage, ...]:
    stages: list[ExecutionStage] = []
    scheduled: dict[int, dict[str, Any]] = {}
    pending_by_activity = _pending_values(pending)
    workflow_started = next(
        (event for event in events if _event_name(event) == "EVENT_TYPE_WORKFLOW_EXECUTION_STARTED"),
        None,
    )
    stages.append(ExecutionStage(
        sequence=1, key="workflow", label="Workflow started",
        status="completed" if workflow_started is not None else "unknown",
        started_at=_event_time(workflow_started) if workflow_started is not None else None,
    ))
    for event in events:
        name = _event_name(event)
        if name == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
            attrs = event.activity_task_scheduled_event_attributes
            activity = _safe_activity_name(attrs.activity_type.name)
            key, label = ACTIVITY_STAGES.get(activity, (f"unknown:{activity}", "Unknown stage"))
            scheduled[event.event_id] = {
                "key": key, "label": label, "scheduled_at": _event_time(event),
                "attempts": pending_by_activity.get(activity, {}).get("attempts"),
                "started_at": None, "known": activity in ACTIVITY_STAGES,
            }
        elif name == "EVENT_TYPE_ACTIVITY_TASK_STARTED":
            attrs = event.activity_task_started_event_attributes
            if attrs.scheduled_event_id in scheduled:
                scheduled[attrs.scheduled_event_id].update(
                    attempts=max(
                        scheduled[attrs.scheduled_event_id]["attempts"] or 1,
                        max(1, min(attrs.attempt, 100)),
                    ),
                    started_at=_event_time(event),
                )
        elif name in {"EVENT_TYPE_ACTIVITY_TASK_COMPLETED", "EVENT_TYPE_ACTIVITY_TASK_FAILED", "EVENT_TYPE_ACTIVITY_TASK_TIMED_OUT", "EVENT_TYPE_ACTIVITY_TASK_CANCELED"}:
            attrs = getattr(event, name.removeprefix("EVENT_TYPE_").lower() + "_event_attributes")
            data = scheduled.pop(attrs.scheduled_event_id, None)
            if data:
                started_at = data["started_at"]
                completed_at = _event_time(event)
                stages.append(ExecutionStage(
                    sequence=len(stages) + 1, key=data["key"], label=data["label"],
                    status=(
                        "unknown"
                        if not data["known"] or name.endswith("CANCELED")
                        else "completed" if name.endswith("COMPLETED") else "failed"
                    ),
                    scheduled_at=data["scheduled_at"], started_at=started_at, completed_at=completed_at,
                    duration_ms=(max(0, int((completed_at - started_at).total_seconds() * 1000)) if started_at else None),
                    attempts=data["attempts"],
                    failure_category=(
                        "activity_failed"
                        if not name.endswith(("COMPLETED", "CANCELED")) and data["known"]
                        else None
                    ),
                    failure_message=(
                        "Activity did not complete"
                        if not name.endswith(("COMPLETED", "CANCELED")) and data["known"]
                        else None
                    ),
                ))
        elif name.startswith("UNKNOWN_EVENT_"):
            event_type = _safe_activity_name(name.removeprefix("UNKNOWN_EVENT_").lower())
            stages.append(ExecutionStage(
                sequence=len(stages) + 1,
                key=f"unknown:event-{event_type}",
                label="Unknown history event",
                status="unknown",
                scheduled_at=_event_time(event),
            ))
    for data in scheduled.values():
        stages.append(ExecutionStage(
            sequence=len(stages) + 1, key=data["key"], label=data["label"],
            status=(
                "unknown"
                if not data["known"] or execution_status != "running"
                else "running"
            ),
            scheduled_at=data["scheduled_at"], started_at=data["started_at"], attempts=data["attempts"],
        ))

    scheduled_activities = {
        data["key"] for data in scheduled.values()
    }
    for activity, data in pending_by_activity.items():
        key, label = ACTIVITY_STAGES.get(
            activity, (f"unknown:{_safe_activity_name(activity)}", "Unknown stage")
        )
        if key in scheduled_activities or any(stage.key == key and stage.status == "running" for stage in stages):
            continue
        stages.append(ExecutionStage(
            sequence=len(stages) + 1,
            key=key,
            label=label,
            status="running" if activity in ACTIVITY_STAGES and execution_status == "running" else "unknown",
            attempts=data["attempts"],
        ))

    failure_stage = getattr(result, "failure_stage", None)
    if isinstance(result, DeploymentFailed) and failure_stage in {"prepare", "deploy", "validate"}:
        pipeline = ("prepare", "deploy", "validate", "publish")
        labels = {value[0]: value[1] for value in ACTIVITY_STAGES.values()}
        if not any(stage.key == failure_stage for stage in stages):
            stages.insert(1, ExecutionStage(
                sequence=1,
                key=failure_stage,
                label=labels[failure_stage],
                status="failed",
                completed_at=result.failed_at,
                failure_category=result.error_type,
                failure_message=SAFE_FAILURE_MESSAGES.get(
                    result.error_type, "Automation operation failed"
                ),
            ))
        existing = {stage.key for stage in stages}
        failed_index = next(
            (index for index, stage in enumerate(stages) if stage.key == failure_stage),
            len(stages) - 1,
        )
        missing = [
            key for key in pipeline[pipeline.index(failure_stage) + 1 : pipeline.index("publish")]
            if key not in existing
        ]
        for offset, key in enumerate(missing, start=1):
            stages.insert(
                failed_index + offset,
                ExecutionStage(
                    sequence=1, key=key, label=labels[key], status="not_reached"
                ),
            )
        for index, stage in enumerate(stages):
            if stage.key == failure_stage and stage.status == "failed":
                stages[index] = stage.model_copy(update={
                    "failure_category": result.error_type,
                    "failure_message": SAFE_FAILURE_MESSAGES.get(
                        result.error_type, "Automation operation failed"
                    ),
                })

    active = any(stage.status == "running" for stage in stages)
    if execution_status == "running" and not active:
        completed_keys = {stage.key for stage in stages if stage.status == "completed"}
        if completed_keys & {"render", "prepare", "deploy", "validate"} and "publish" not in completed_keys:
            stages.append(ExecutionStage(
                sequence=1, key="finalizing", label="Finalizing workflow", status="running"
            ))

    return tuple(
        stage.model_copy(update={"sequence": index})
        for index, stage in enumerate(stages[:64], start=1)
    )


async def _retained_activity_results(client: Any, events: list[Any]) -> dict[str, Any]:
    scheduled: dict[int, str] = {}
    retained: dict[str, Any] = {}
    result_types = {
        "prepare_device_deployment": PreparedDeployment,
        "deploy_device_artifact": DeploymentResult,
        "validate_device_state": DeviceValidationResult,
    }
    for event in events:
        name = _event_name(event)
        if name == "EVENT_TYPE_ACTIVITY_TASK_SCHEDULED":
            scheduled[event.event_id] = (
                event.activity_task_scheduled_event_attributes.activity_type.name
            )
        elif name == "EVENT_TYPE_ACTIVITY_TASK_COMPLETED":
            attrs = event.activity_task_completed_event_attributes
            activity = scheduled.get(attrs.scheduled_event_id)
            model_type = result_types.get(activity)
            if model_type is not None:
                value = await _decode_payloads(client, attrs.result, (model_type,))
                if value is not None:
                    retained[activity] = value
    return retained


async def get_workflow_detail(
    client: Any,
    workflow_id: str,
    run_id: str | None,
    artifact_root: Path,
    *,
    history_timeout: int = 8,
) -> WorkflowDetail | None:
    validate_workflow_id(workflow_id)
    handle = client.get_workflow_handle(workflow_id, run_id=run_id)
    try:
        execution = await asyncio.wait_for(handle.describe(), timeout=history_timeout)
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            return None
        raise
    try:
        request, result, events = await asyncio.wait_for(
            _hydrate(client, execution, all_events=True), timeout=history_timeout
        )
    except (RPCError, TimeoutError):
        return WorkflowDetail(
            summary=_summary(execution, None, None),
            stages=(),
            history_status=_history_unavailable(),
        )
    if not events:
        return WorkflowDetail(
            summary=_summary(execution, request, result),
            stages=(),
            history_status=_history_unavailable(),
        )
    pending = tuple(
        getattr(getattr(execution, "raw_description", None), "pending_activities", ())
    )
    summary = _summary(execution, request, result)
    stages = _stages(
        events,
        execution_status=summary.execution_status,
        result=result,
        pending=pending,
    )
    current = next(
        (stage.key for stage in reversed(stages) if stage.status in {"running", "failed", "unknown"}),
        next((stage.key for stage in reversed(stages) if stage.key != "workflow"), None),
    )
    summary = summary.model_copy(update={"current_stage": current})
    retained = await _retained_activity_results(client, events)
    prepared = retained.get("prepare_device_deployment")
    deployment_result = retained.get("deploy_device_artifact")
    validation_result = retained.get("validate_device_state")
    artifact_identity = (
        getattr(deployment_result, "artifact", None)
        or getattr(prepared, "artifact", None)
    )
    artifact = _artifact(result, artifact_root) or _artifact(
        artifact_identity, artifact_root
    )
    deployment = deployment_from_summary(summary, result, artifact_root) if summary.kind == "deployment" else None
    if deployment is not None:
        deployment = deployment.model_copy(update={
            "artifact": artifact,
            "deployed_at": (
                getattr(result, "deployed_at", None)
                or getattr(deployment_result, "deployed_at", None)
            ),
        })
    validation = None
    if isinstance(validation_result, DeviceValidationResult):
        validation = ValidationSummary(
            status=validation_result.status,
            validated_at=validation_result.validated_at,
            checks_total=len(validation_result.checks),
            checks_failed=sum(
                check.status == "failed" for check in validation_result.checks
            ),
        )
    elif isinstance(result, DeploymentCompleted):
        validation = ValidationSummary(status="passed")
    elif isinstance(result, DeploymentFailed) and result.failure_stage == "validate":
        validation = ValidationSummary(status="failed")
    failure = None
    category = getattr(result, "error_type", None)
    if category:
        failure = SafeFailureSummary(
            stage=getattr(result, "failure_stage", None), category=category,
            message=SAFE_FAILURE_MESSAGES.get(category, "Automation operation failed"),
        )
    elif summary.outcome in {
        "execution_failed", "execution_canceled", "execution_terminated", "execution_timed_out"
    }:
        failure = SafeFailureSummary(
            stage="execution",
            category=summary.outcome,
            message=SAFE_FAILURE_MESSAGES[summary.outcome],
        )
    return WorkflowDetail(
        summary=summary, stages=stages, artifact=artifact, deployment=deployment,
        validation=validation, failure=failure, history_status=_available(),
    )


__all__ = [
    "get_workflow_detail", "list_deployments", "list_workflow_projections",
    "list_workflow_summaries", "validate_workflow_id",
]
