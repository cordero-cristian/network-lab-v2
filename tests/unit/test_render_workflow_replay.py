from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import pytest
from temporalio import activity, workflow
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowHistory
from temporalio.common import RetryPolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from network_automation.events.models import (
    ArtifactMetadata,
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
    workflow_id_for,
)
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow


FEATURE003_RENDER_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    non_retryable_error_types=(
        "intent_invalid",
        "nautobot_rejected",
        "unsupported_platform",
        "render_invalid",
        "internal_error",
    ),
)
FEATURE003_PUBLISH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)


@workflow.defn(name="RenderDeviceConfigWorkflow")
class AcceptedFeature003RenderWorkflow:
    """Frozen accepted command producer used only to generate replay histories."""

    @workflow.run
    async def run(
        self, request: RenderDeviceConfigRequest
    ) -> RenderCompleted | RenderFailed:
        workflow_id = workflow.info().workflow_id
        try:
            artifact = await workflow.execute_activity(
                "render_device_artifact",
                request,
                result_type=ArtifactMetadata,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=FEATURE003_RENDER_RETRY_POLICY,
            )
        except ActivityError as exc:
            cause = exc.cause
            allowed_types = {
                "nautobot_unavailable",
                "artifact_unavailable",
                "intent_invalid",
                "nautobot_rejected",
                "unsupported_platform",
                "render_invalid",
                "internal_error",
            }
            known = isinstance(cause, ApplicationError) and cause.type in allowed_types
            failed = RenderFailed(
                event_type="network.render.failed",
                event_version=1,
                event_id=workflow.uuid4(),
                correlation_id=request.correlation_id,
                device_name=request.device_name,
                workflow_id=workflow_id,
                error_type=cause.type if known else "internal_error",
                error_message=(
                    cause.message if known else "render activity did not complete"
                ),
                failed_at=workflow.now(),
            )
            await workflow.execute_activity(
                "publish_render_result",
                failed,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=FEATURE003_PUBLISH_RETRY_POLICY,
            )
            return failed

        completed = RenderCompleted(
            event_type="network.render.completed",
            event_version=1,
            event_id=workflow.uuid4(),
            correlation_id=request.correlation_id,
            device_name=request.device_name,
            workflow_id=workflow_id,
            artifact_path=artifact.artifact_path,
            completed_at=workflow.now(),
        )
        await workflow.execute_activity(
            "publish_render_result",
            completed,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=FEATURE003_PUBLISH_RETRY_POLICY,
        )
        return completed


@dataclass(frozen=True)
class AcceptedExecution:
    request: RenderDeviceConfigRequest
    result: RenderCompleted | RenderFailed
    history: WorkflowHistory


async def _generate_accepted_feature003_history(*, fail: bool) -> AcceptedExecution:
    suffix = "failure" if fail else "success"
    request = RenderDeviceConfigRequest(
        event_id=UUID(
            "77ee1844-cd3a-4c45-8de7-3dd76fc7da2d"
            if not fail
            else "dbe54486-a5cc-483f-8a9d-8fa5d8ea5128"
        ),
        correlation_id=UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80"),
        device_name="leaf01",
    )

    @activity.defn(name="render_device_artifact")
    async def render(value: RenderDeviceConfigRequest) -> ArtifactMetadata:
        if fail:
            raise ApplicationError(
                "render request cannot be completed safely",
                type="intent_invalid",
                non_retryable=True,
            )
        return ArtifactMetadata(
            device_name=value.device_name,
            artifact_path="artifacts/configs/leaf01.cfg",
        )

    @activity.defn(name="publish_render_result")
    async def publish(_: RenderCompleted | RenderFailed) -> None:
        return None

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue=f"feature003-replay-{suffix}",
            workflows=[AcceptedFeature003RenderWorkflow],
            activities=[render, publish],
        ):
            handle = await environment.client.start_workflow(
                "RenderDeviceConfigWorkflow",
                request,
                result_type=RenderFailed if fail else RenderCompleted,
                id=workflow_id_for(request.event_id),
                task_queue=f"feature003-replay-{suffix}",
            )
            result = await handle.result()
            history = await handle.fetch_history()
    return AcceptedExecution(request=request, result=result, history=history)


async def _decode_single(payloads: object, result_type: type[object]) -> object:
    values = await pydantic_data_converter.decode(payloads, [result_type])  # type: ignore[arg-type]
    assert len(values) == 1
    return values[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True], ids=["success", "failure"])
async def test_accepted_feature003_histories_replay_without_command_or_payload_changes(
    fail: bool,
) -> None:
    accepted = await _generate_accepted_feature003_history(fail=fail)
    scheduled = [
        event.activity_task_scheduled_event_attributes
        for event in accepted.history.events
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    ]
    completed = next(
        event.workflow_execution_completed_event_attributes
        for event in accepted.history.events
        if event.event_type == EventType.EVENT_TYPE_WORKFLOW_EXECUTION_COMPLETED
    )

    assert [item.activity_type.name for item in scheduled] == [
        "render_device_artifact",
        "publish_render_result",
    ]
    assert await _decode_single(scheduled[0].input.payloads, RenderDeviceConfigRequest) == (
        accepted.request
    )
    publish_type = RenderFailed if fail else RenderCompleted
    assert await _decode_single(scheduled[1].input.payloads, publish_type) == accepted.result
    assert await _decode_single(completed.result.payloads, publish_type) == accepted.result

    replay_result = await Replayer(
        workflows=[RenderDeviceConfigWorkflow],
        data_converter=pydantic_data_converter,
    ).replay_workflow(accepted.history)
    assert replay_result.replay_failure is None
