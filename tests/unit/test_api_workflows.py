import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from temporalio.api.enums.v1 import EventType
from temporalio.service import RPCError, RPCStatusCode

from network_automation.api.workflows import (
    _artifact,
    _stages,
    _summary,
    get_workflow_detail,
    list_workflow_summaries,
    validate_workflow_id,
)
from network_automation.events.models import DeploymentFailed


class EmptyEvents:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class Handle:
    def fetch_history_events(self, **kwargs):
        return EmptyEvents()


class Temporal:
    def __init__(self, count: int):
        now = datetime.now(timezone.utc)
        self.executions = [
            SimpleNamespace(
                id=f"deploy-device-config:{uuid4()}", run_id=str(uuid4()),
                workflow_type="RenderDeviceConfigWorkflow", status=SimpleNamespace(name="RUNNING"),
                start_time=now, close_time=None,
            )
            for _ in range(count)
        ]

    async def list_workflows(self, **kwargs):
        for value in self.executions[: kwargs["limit"]]:
            yield value

    def get_workflow_handle(self, workflow_id, *, run_id):
        return Handle()


def test_workflow_lists_default_to_bounded_shallow_data() -> None:
    result = asyncio.run(list_workflow_summaries(Temporal(60), limit=50))

    assert result.count == 50
    assert all(item.execution_status == "running" for item in result.items)
    assert all(item.outcome == "running" for item in result.items)


def test_overview_hydration_is_capped_at_eight() -> None:
    temporal = Temporal(20)
    calls = 0

    def get_handle(workflow_id, run_id):
        nonlocal calls
        calls += 1
        return Handle()

    temporal.get_workflow_handle = get_handle
    asyncio.run(list_workflow_summaries(temporal, limit=20, hydration_limit=20))

    assert calls == 8


def test_workflow_id_validation_accepts_only_exact_owned_prefix_and_uuid() -> None:
    valid = f"render-device-config:{uuid4()}"
    assert validate_workflow_id(valid) == valid
    for invalid in ("other:" + str(uuid4()), "render-device-config:not-a-uuid", valid + "x"):
        try:
            validate_workflow_id(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)


def test_handled_deployment_failure_is_distinct_from_completed_execution() -> None:
    event_id = uuid4()
    run_id = uuid4()
    now = datetime.now(timezone.utc)
    execution = SimpleNamespace(
        id=f"deploy-device-config:{event_id}", run_id=str(run_id),
        status=SimpleNamespace(name="COMPLETED"), start_time=now, close_time=now,
    )
    request = SimpleNamespace(event_id=event_id, correlation_id=uuid4(), device_name="leaf01")
    result = DeploymentFailed(
        event_type="network.deployment.failed", event_version=1, event_id=uuid4(),
        correlation_id=request.correlation_id, device_name="leaf01", workflow_id=execution.id,
        failure_stage="prepare", error_type="intent_invalid",
        error_message="device intent validation failed", failed_at=now,
        artifact_sha256=None, artifact_bytes=None, deployed_at=None,
    )

    summary = _summary(execution, request, result)

    assert summary.execution_status == "completed"
    assert summary.outcome == "deployment_failed"
    assert summary.failure_category == "intent_invalid"


class EventTime:
    def __init__(self, value):
        self.value = value

    def ToDatetime(self):
        return self.value


def _event(event_type, event_id, attribute_name=None, attributes=None):
    value = SimpleNamespace(
        event_type=event_type,
        event_id=event_id,
        event_time=EventTime(datetime.now(timezone.utc)),
    )
    if attribute_name:
        setattr(value, attribute_name, attributes)
    return value


def _activity_events(activity: str, *, terminal: str = "completed"):
    scheduled = _event(
        EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
        2,
        "activity_task_scheduled_event_attributes",
        SimpleNamespace(activity_type=SimpleNamespace(name=activity)),
    )
    started = _event(
        EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED,
        3,
        "activity_task_started_event_attributes",
        SimpleNamespace(scheduled_event_id=2, attempt=2),
    )
    event_type = {
        "completed": EventType.EVENT_TYPE_ACTIVITY_TASK_COMPLETED,
        "failed": EventType.EVENT_TYPE_ACTIVITY_TASK_FAILED,
    }[terminal]
    terminal_event = _event(
        event_type,
        4,
        f"activity_task_{terminal}_event_attributes",
        SimpleNamespace(scheduled_event_id=2),
    )
    return [scheduled, started, terminal_event]


def test_stage_mapping_does_not_invent_start_and_keeps_unknown_activity_unknown() -> None:
    missing = _stages([], execution_status="completed", result=None)
    unknown = _stages(
        _activity_events("future_activity"),
        execution_status="completed",
        result=None,
    )

    assert missing[0].key == "workflow"
    assert missing[0].status == "unknown"
    assert unknown[-1].key == "unknown:future_activity"
    assert unknown[-1].status == "unknown"


def test_stage_mapping_keeps_unknown_history_event_visible() -> None:
    stages = _stages(
        [_event(9999, 1)], execution_status="completed", result=None
    )

    assert stages[0].status == "unknown"
    assert stages[1].key == "unknown:event-9999"
    assert stages[1].status == "unknown"


def test_stage_mapping_marks_not_reached_and_uses_safe_failure_category() -> None:
    now = datetime.now(timezone.utc)
    result = DeploymentFailed(
        event_type="network.deployment.failed", event_version=1, event_id=uuid4(),
        correlation_id=uuid4(), device_name="leaf01",
        workflow_id=f"deploy-device-config:{uuid4()}", failure_stage="prepare",
        error_type="intent_invalid", error_message="device intent validation failed",
        failed_at=now, artifact_sha256=None, artifact_bytes=None, deployed_at=None,
    )
    events = [_event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED, 1)]
    events.extend(_activity_events("prepare_device_deployment", terminal="failed"))

    stages = _stages(events, execution_status="completed", result=result)

    assert [(stage.key, stage.status) for stage in stages] == [
        ("workflow", "completed"),
        ("prepare", "failed"),
        ("deploy", "not_reached"),
        ("validate", "not_reached"),
    ]
    assert stages[1].failure_category == "intent_invalid"
    assert "device intent validation failed" not in " ".join(
        stage.failure_message or "" for stage in stages
    ).lower()

    retained_result_only = _stages(
        events[:1], execution_status="completed", result=result
    )
    assert [(stage.key, stage.status) for stage in retained_result_only] == [
        ("workflow", "completed"),
        ("prepare", "failed"),
        ("deploy", "not_reached"),
        ("validate", "not_reached"),
    ]


def test_stage_mapping_uses_pending_attempts_and_finalizing_state() -> None:
    start = _event(EventType.EVENT_TYPE_WORKFLOW_EXECUTION_STARTED, 1)
    scheduled = _activity_events("render_device_artifact")[:1]
    pending = (
        SimpleNamespace(
            activity_type=SimpleNamespace(name="render_device_artifact"), attempt=3
        ),
    )
    running = _stages(
        [start, *scheduled], execution_status="running", result=None, pending=pending
    )
    finished_activity = _stages(
        [start, *_activity_events("render_device_artifact")],
        execution_status="running",
        result=None,
    )

    assert running[-1].status == "running"
    assert running[-1].attempts == 3
    assert finished_activity[-1].key == "finalizing"
    assert finished_activity[-1].status == "running"


def test_workflow_detail_preserves_visibility_when_full_history_is_unavailable() -> None:
    workflow_id = f"deploy-device-config:{uuid4()}"
    run_id = str(uuid4())
    now = datetime.now(timezone.utc)
    execution = SimpleNamespace(
        id=workflow_id,
        run_id=run_id,
        workflow_type="RenderDeviceConfigWorkflow",
        status=SimpleNamespace(name="RUNNING"),
        start_time=now,
        close_time=None,
        raw_description=SimpleNamespace(pending_activities=()),
    )

    class FailingEvents:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RPCError(
                "retained history unavailable", RPCStatusCode.UNAVAILABLE, b""
            )

    class DetailHandle:
        async def describe(self):
            return execution

        def fetch_history_events(self, **kwargs):
            return FailingEvents()

    class DetailTemporal:
        def __init__(self):
            self.requested = []

        def get_workflow_handle(self, requested_workflow_id, *, run_id):
            self.requested.append((requested_workflow_id, run_id))
            return DetailHandle()

    temporal = DetailTemporal()
    detail = asyncio.run(
        get_workflow_detail(
            temporal, workflow_id, run_id, Path("artifacts"), history_timeout=1
        )
    )

    assert detail is not None
    assert detail.summary.workflow_id == workflow_id
    assert detail.summary.run_id == UUID(run_id)
    assert detail.summary.execution_status == "running"
    assert detail.stages == ()
    assert detail.history_status.status == "degraded"
    assert detail.history_status.code == "history_unavailable"
    assert temporal.requested == [(workflow_id, run_id), (workflow_id, run_id)]


def test_artifact_mapper_rejects_symlink_escape(tmp_path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside.cfg"
    outside.write_text("secret")
    (root / "escape.cfg").symlink_to(outside)
    result = SimpleNamespace(
        artifact_path=str(root / "escape.cfg"),
        artifact_sha256="0" * 64,
        artifact_bytes=6,
    )

    assert _artifact(result, root) is None
