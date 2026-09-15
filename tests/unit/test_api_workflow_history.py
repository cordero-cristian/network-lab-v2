import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from temporalio.api.enums.v1 import EventType

from network_automation.api import workflows
from network_automation.events.models import (
    DeploymentCompleted,
    DeploymentFailed,
    DeployDeviceConfigRequest,
    RenderDeviceConfigRequest,
)


class EventTime:
    def ToDatetime(self):
        return datetime.now(timezone.utc)


def event(event_type, event_id, attribute_name=None, attributes=None):
    value = SimpleNamespace(event_type=event_type, event_id=event_id, event_time=EventTime())
    if attribute_name:
        setattr(value, attribute_name, attributes)
    return value


def test_payload_correlation_rejects_wrong_kind_event_and_result_identity() -> None:
    event_id = uuid4()
    correlation_id = uuid4()
    execution = SimpleNamespace(id=f"deploy-device-config:{event_id}")
    request = DeployDeviceConfigRequest(
        operation="deploy", event_id=event_id, correlation_id=correlation_id, device_name="leaf01"
    )
    result = DeploymentCompleted(
        event_type="network.deployment.completed",
        event_version=1,
        event_id=uuid4(),
        correlation_id=correlation_id,
        device_name="leaf01",
        workflow_id=execution.id,
        artifact_path="artifacts/configs/leaf01.cfg",
        artifact_sha256="0" * 64,
        artifact_bytes=1,
        deployed_at=datetime.now(timezone.utc),
        validation_status="passed",
        completed_at=datetime.now(timezone.utc),
    )

    assert workflows._correlate_payloads(execution, request, result) == (request, result)

    wrong_event = request.model_copy(update={"event_id": uuid4()})
    assert workflows._correlate_payloads(execution, wrong_event, result) == (None, None)

    wrong_kind = RenderDeviceConfigRequest(
        event_id=event_id, correlation_id=correlation_id, device_name="leaf01"
    )
    assert workflows._correlate_payloads(execution, wrong_kind, result) == (None, None)

    wrong_result = result.model_copy(
        update={"workflow_id": f"deploy-device-config:{uuid4()}"}
    )
    assert workflows._correlate_payloads(execution, request, wrong_result) == (request, None)

    wrong_device = result.model_copy(update={"device_name": "leaf02"})
    assert workflows._correlate_payloads(execution, request, wrong_device) == (request, None)


def test_failed_result_does_not_synthesize_an_artifact_path(tmp_path) -> None:
    result = DeploymentFailed(
        event_type="network.deployment.failed",
        event_version=1,
        event_id=uuid4(),
        correlation_id=uuid4(),
        device_name="leaf01",
        workflow_id=f"deploy-device-config:{uuid4()}",
        failure_stage="deploy",
        error_type="device_unavailable",
        error_message="device unavailable",
        failed_at=datetime.now(timezone.utc),
        artifact_sha256="0" * 64,
        artifact_bytes=1,
        deployed_at=None,
    )

    assert workflows._artifact(result, tmp_path) is None


def test_canceled_activity_is_unknown_without_failure_claim() -> None:
    scheduled = event(
        EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED,
        2,
        "activity_task_scheduled_event_attributes",
        SimpleNamespace(activity_type=SimpleNamespace(name="deploy_device_artifact")),
    )
    started = event(
        EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED,
        3,
        "activity_task_started_event_attributes",
        SimpleNamespace(scheduled_event_id=2, attempt=1),
    )
    canceled = event(
        EventType.EVENT_TYPE_ACTIVITY_TASK_CANCELED,
        4,
        "activity_task_canceled_event_attributes",
        SimpleNamespace(scheduled_event_id=2),
    )

    stage = workflows._stages(
        [scheduled, started, canceled], execution_status="canceled", result=None
    )[-1]

    assert stage.status == "unknown"
    assert stage.failure_category is None
    assert stage.failure_message is None


def test_shallow_hydration_never_exceeds_concurrency_four() -> None:
    now = datetime.now(timezone.utc)

    class Temporal:
        def __init__(self):
            self.active = 0
            self.maximum = 0
            self.executions = [
                SimpleNamespace(
                    id=f"render-device-config:{uuid4()}",
                    run_id=str(uuid4()),
                    workflow_type="RenderDeviceConfigWorkflow",
                    status=SimpleNamespace(name="RUNNING"),
                    start_time=now,
                    close_time=None,
                )
                for _ in range(12)
            ]

        async def list_workflows(self, **kwargs):
            for execution in self.executions:
                yield execution

        def get_workflow_handle(self, workflow_id, *, run_id):
            temporal = self

            class Handle:
                def fetch_history_events(self, **kwargs):
                    async def values():
                        temporal.active += 1
                        temporal.maximum = max(temporal.maximum, temporal.active)
                        await asyncio.sleep(0.01)
                        temporal.active -= 1
                        if False:
                            yield None

                    return values()

            return Handle()

    temporal = Temporal()
    asyncio.run(
        workflows.list_workflow_summaries(
            temporal, limit=12, hydration_concurrency=4
        )
    )

    assert temporal.maximum == 4
