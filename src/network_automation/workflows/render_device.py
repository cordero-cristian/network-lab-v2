"""Durable coordination for one requested configuration artifact."""

from __future__ import annotations

from datetime import datetime, timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from network_automation.events.models import (
        ArtifactMetadata,
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


def _outcome_timestamp(deployed_at: datetime) -> datetime:
    return max(workflow.now(), deployed_at)


PUBLISH_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=5,
)
PREPARE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=3,
    non_retryable_error_types=(
        "intent_invalid",
        "nautobot_rejected",
        "unsupported_platform",
        "management_address_invalid",
        "artifact_invalid",
        "artifact_mismatch",
        "device_settings_missing",
        "internal_error",
    ),
)
DEPLOY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    non_retryable_error_types=(
        "device_authentication_failed",
        "device_identity_mismatch",
        "device_platform_mismatch",
        "configuration_rejected",
        "artifact_mismatch",
        "internal_error",
    ),
)
VALIDATE_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=5),
    maximum_attempts=12,
    non_retryable_error_types=(
        "device_authentication_failed",
        "device_state_invalid",
        "validation_failed",
        "internal_error",
    ),
)

_DEPLOYMENT_FAILURE_TYPES = {
    "prepare": {
        "nautobot_unavailable",
        "nautobot_rejected",
        "intent_invalid",
        "unsupported_platform",
        "management_address_invalid",
        "artifact_unavailable",
        "artifact_invalid",
        "artifact_mismatch",
        "device_settings_missing",
    },
    "deploy": {
        "device_unavailable",
        "device_authentication_failed",
        "device_identity_mismatch",
        "device_platform_mismatch",
        "configuration_rejected",
        "artifact_mismatch",
        "internal_error",
    },
    "validate": {
        "device_unavailable",
        "device_authentication_failed",
        "device_state_invalid",
        "validation_not_converged",
        "validation_failed",
        "internal_error",
    },
}


def _deployment_error(
    exc: ActivityError, stage: str
) -> tuple[str, str]:
    cause = exc.cause
    known_application_error = (
        isinstance(cause, ApplicationError)
        and cause.type in _DEPLOYMENT_FAILURE_TYPES[stage]
    )
    if known_application_error:
        return cause.type, cause.message
    return "internal_error", f"deployment {stage} activity did not complete"


@workflow.defn
class RenderDeviceConfigWorkflow:
    @workflow.run
    async def run(
        self, request: RenderDeviceConfigRequest | DeployDeviceConfigRequest
    ) -> RenderCompleted | RenderFailed | DeploymentCompleted | DeploymentFailed:
        if isinstance(request, DeployDeviceConfigRequest):
            return await self._run_deployment(request)

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

    async def _run_deployment(
        self, request: DeployDeviceConfigRequest
    ) -> DeploymentCompleted | DeploymentFailed:
        workflow_id = workflow.info().workflow_id
        try:
            prepared = await workflow.execute_activity(
                "prepare_device_deployment",
                request,
                result_type=PreparedDeployment,
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=PREPARE_RETRY_POLICY,
            )
        except ActivityError as exc:
            error_type, error_message = _deployment_error(exc, "prepare")
            failed = DeploymentFailed(
                event_type="network.deployment.failed",
                event_version=1,
                event_id=workflow.uuid4(),
                correlation_id=request.correlation_id,
                device_name=request.device_name,
                workflow_id=workflow_id,
                failure_stage="prepare",
                error_type=error_type,
                error_message=error_message,
                failed_at=workflow.now(),
                artifact_sha256=None,
                artifact_bytes=None,
                deployed_at=None,
            )
            await workflow.execute_activity(
                "publish_render_result",
                failed,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=PUBLISH_RETRY_POLICY,
            )
            return failed

        try:
            deployment = await workflow.execute_activity(
                "deploy_device_artifact",
                prepared,
                result_type=DeploymentResult,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEPLOY_RETRY_POLICY,
            )
        except ActivityError as exc:
            error_type, error_message = _deployment_error(exc, "deploy")
            failed = DeploymentFailed(
                event_type="network.deployment.failed",
                event_version=1,
                event_id=workflow.uuid4(),
                correlation_id=request.correlation_id,
                device_name=request.device_name,
                workflow_id=workflow_id,
                failure_stage="deploy",
                error_type=error_type,
                error_message=error_message,
                failed_at=workflow.now(),
                artifact_sha256=prepared.artifact.sha256,
                artifact_bytes=prepared.artifact.byte_count,
                deployed_at=None,
            )
            await workflow.execute_activity(
                "publish_render_result",
                failed,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=PUBLISH_RETRY_POLICY,
            )
            return failed

        try:
            validation = await workflow.execute_activity(
                "validate_device_state",
                prepared,
                result_type=DeviceValidationResult,
                start_to_close_timeout=timedelta(seconds=15),
                schedule_to_close_timeout=timedelta(seconds=90),
                retry_policy=VALIDATE_RETRY_POLICY,
            )
        except ActivityError as exc:
            error_type, error_message = _deployment_error(exc, "validate")
            failed = DeploymentFailed(
                event_type="network.deployment.failed",
                event_version=1,
                event_id=workflow.uuid4(),
                correlation_id=request.correlation_id,
                device_name=request.device_name,
                workflow_id=workflow_id,
                failure_stage="validate",
                error_type=error_type,
                error_message=error_message,
                failed_at=_outcome_timestamp(deployment.deployed_at),
                artifact_sha256=prepared.artifact.sha256,
                artifact_bytes=prepared.artifact.byte_count,
                deployed_at=deployment.deployed_at,
            )
            await workflow.execute_activity(
                "publish_render_result",
                failed,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=PUBLISH_RETRY_POLICY,
            )
            return failed

        if validation.status == "failed":
            failed = DeploymentFailed(
                event_type="network.deployment.failed",
                event_version=1,
                event_id=workflow.uuid4(),
                correlation_id=request.correlation_id,
                device_name=request.device_name,
                workflow_id=workflow_id,
                failure_stage="validate",
                error_type="validation_failed",
                error_message="device state did not match intended invariants",
                failed_at=_outcome_timestamp(deployment.deployed_at),
                artifact_sha256=prepared.artifact.sha256,
                artifact_bytes=prepared.artifact.byte_count,
                deployed_at=deployment.deployed_at,
            )
            await workflow.execute_activity(
                "publish_render_result",
                failed,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=PUBLISH_RETRY_POLICY,
            )
            return failed

        completed = DeploymentCompleted(
            event_type="network.deployment.completed",
            event_version=1,
            event_id=workflow.uuid4(),
            correlation_id=request.correlation_id,
            device_name=request.device_name,
            workflow_id=workflow_id,
            artifact_path=prepared.artifact.artifact_path,
            artifact_sha256=prepared.artifact.sha256,
            artifact_bytes=prepared.artifact.byte_count,
            deployed_at=deployment.deployed_at,
            validation_status="passed",
            completed_at=_outcome_timestamp(deployment.deployed_at),
        )
        await workflow.execute_activity(
            "publish_render_result",
            completed,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=PUBLISH_RETRY_POLICY,
        )
        return completed
