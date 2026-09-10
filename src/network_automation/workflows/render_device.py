"""Durable coordination for one requested configuration artifact."""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from network_automation.events.models import (
        ArtifactMetadata,
        RenderCompleted,
        RenderDeviceConfigRequest,
        RenderFailed,
    )

RENDER_RETRY_POLICY = RetryPolicy(
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
PUBLISH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)


@workflow.defn
class RenderDeviceConfigWorkflow:
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
                retry_policy=RENDER_RETRY_POLICY,
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
            known_application_error = (
                isinstance(cause, ApplicationError) and cause.type in allowed_types
            )
            error_type = cause.type if known_application_error else "internal_error"
            error_message = (
                cause.message if known_application_error else "render activity did not complete"
            )
            failed = RenderFailed(
                event_type="network.render.failed",
                event_version=1,
                event_id=workflow.uuid4(),
                correlation_id=request.correlation_id,
                device_name=request.device_name,
                workflow_id=workflow_id,
                error_type=error_type,
                error_message=error_message,
                failed_at=workflow.now(),
            )
            await workflow.execute_activity(
                "publish_render_result",
                failed,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=PUBLISH_RETRY_POLICY,
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
            retry_policy=PUBLISH_RETRY_POLICY,
        )
        return completed
