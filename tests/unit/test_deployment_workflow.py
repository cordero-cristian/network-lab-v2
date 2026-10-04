from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from google.protobuf.duration_pb2 import Duration
from temporalio import activity
from temporalio.api.enums.v1 import EventType
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from network_automation.events.models import (
    ArtifactIdentity,
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
    ValidationCheck,
    deployment_workflow_id_for,
    workflow_id_for,
)
from network_automation.workflows import render_device
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow


EVENT_ID = UUID("08660568-3d4c-4901-9a77-8a4fb0e68072")
CORRELATION_ID = UUID("eaf41a9d-9cb8-4de0-bd68-32bbc47e5030")
DIGEST = "cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887"
DEPLOYED_AT = datetime(2026, 9, 10, 18, 0, 4, tzinfo=timezone.utc)


def test_outcome_timestamp_never_precedes_worker_deployment_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        render_device.workflow,
        "now",
        lambda: DEPLOYED_AT - timedelta(seconds=5),
    )

    assert render_device._outcome_timestamp(DEPLOYED_AT) == DEPLOYED_AT


def _deployment_request() -> DeployDeviceConfigRequest:
    return DeployDeviceConfigRequest(
        operation="deploy",
        event_id=EVENT_ID,
        correlation_id=CORRELATION_ID,
        device_name="f004-leaf01",
    )


def _artifact() -> ArtifactIdentity:
    return ArtifactIdentity(
        device_name="f004-leaf01",
        artifact_path="artifacts/configs/f004-leaf01.cfg",
        sha256=DIGEST,
        byte_count=1248,
    )


def _prepared() -> PreparedDeployment:
    return PreparedDeployment.model_validate(
        {
            "artifact": _artifact().model_dump(),
            "target": {
                "device_name": "f004-leaf01",
                "management_address": "172.31.46.12",
                "platform": "nokia_srl",
                "gnmi_port": 57401,
                "tls_mode": "insecure",
            },
            "expected_state": {
                "device_name": "f004-leaf01",
                "loopback_name": "system0",
                "loopback_prefix": "10.0.0.2/32",
                "routed_interfaces": (
                    {
                        "name": "ethernet-1/1",
                        "ipv4_prefix": "192.0.2.1/31",
                        "require_oper_up": True,
                    },
                ),
                "local_asn": 65001,
                "bgp_neighbors": (
                    {"address": "192.0.2.0", "remote_asn": 65000},
                ),
            },
        }
    )


def _duration(seconds: int) -> Duration:
    return Duration(seconds=seconds)


def _deployment_result(prepared: PreparedDeployment) -> DeploymentResult:
    return DeploymentResult(
        artifact=prepared.artifact,
        device_name=prepared.target.device_name,
        management_address=prepared.target.management_address,
        deployed_at=DEPLOYED_AT,
    )


def _validation_result(prepared: PreparedDeployment) -> DeviceValidationResult:
    return DeviceValidationResult(
        device_name=prepared.target.device_name,
        status="passed",
        checks=(
            ValidationCheck(
                name="system.hostname",
                status="passed",
                expected=prepared.expected_state.device_name,
                observed=prepared.expected_state.device_name,
                message=None,
            ),
        ),
        validated_at=datetime(2026, 9, 10, 18, 0, 12, tzinfo=timezone.utc),
    )


def _scheduled_activities(history: object) -> list[object]:
    return [
        event.activity_task_scheduled_event_attributes
        for event in history.events  # type: ignore[attr-defined]
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    ]


@pytest.mark.asyncio
async def test_deployment_success_uses_only_the_four_ordered_activity_barriers() -> None:
    # Fail promptly during the TDD stage instead of leaving Temporal to retry an
    # input-decoding workflow task until the workflow execution timeout.
    assert "DeployDeviceConfigRequest" in str(
        RenderDeviceConfigWorkflow.run.__annotations__["request"]
    )

    calls: list[tuple[str, object]] = []
    prepared = _prepared()

    @activity.defn(name="prepare_device_deployment")
    async def prepare(value: DeployDeviceConfigRequest) -> PreparedDeployment:
        calls.append(("prepare", value))
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        calls.append(("deploy", value))
        return DeploymentResult(
            artifact=value.artifact,
            device_name=value.target.device_name,
            management_address=value.target.management_address,
            deployed_at=DEPLOYED_AT,
        )

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        calls.append(("validate", value))
        return DeviceValidationResult(
            device_name=value.target.device_name,
            status="passed",
            checks=(
                ValidationCheck(
                    name="system.hostname",
                    status="passed",
                    expected=value.expected_state.device_name,
                    observed=value.expected_state.device_name,
                    message=None,
                ),
            ),
            validated_at=datetime(2026, 9, 10, 18, 0, 12, tzinfo=timezone.utc),
        )

    @activity.defn(name="publish_render_result")
    async def publish(
        value: DeploymentCompleted | DeploymentFailed | RenderCompleted | RenderFailed,
    ) -> None:
        calls.append(("publish", value))

    request = _deployment_request()
    workflow_id = deployment_workflow_id_for(request.event_id)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-success",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            handle = await environment.client.start_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=workflow_id,
                task_queue="deployment-workflow-success",
                execution_timeout=timedelta(minutes=10),
            )
            result = await handle.result()
            history = await handle.fetch_history()

    assert [name for name, _ in calls] == ["prepare", "deploy", "validate", "publish"]
    assert all(name != "render" for name, _ in calls)
    assert calls[0][1] == request
    assert calls[1][1] == calls[2][1] == prepared
    assert calls[3][1] == result

    assert isinstance(result, DeploymentCompleted)
    assert result.correlation_id == request.correlation_id
    assert result.device_name == request.device_name
    assert result.workflow_id == workflow_id
    assert result.artifact_path == prepared.artifact.artifact_path
    assert result.artifact_sha256 == DIGEST
    assert result.artifact_bytes == 1248
    assert result.deployed_at == DEPLOYED_AT
    assert result.validation_status == "passed"
    assert result.completed_at.utcoffset() == timedelta(0)
    assert result.completed_at >= DEPLOYED_AT
    assert result.event_id.version == 4

    scheduled = _scheduled_activities(history)
    assert [item.activity_type.name for item in scheduled] == [
        "prepare_device_deployment",
        "deploy_device_artifact",
        "validate_device_state",
        "publish_render_result",
    ]
    expected = (
        (
            60,
            None,
            1,
            2.0,
            5,
            3,
            (
                "intent_invalid",
                "nautobot_rejected",
                "unsupported_platform",
                "management_address_invalid",
                "artifact_invalid",
                "artifact_mismatch",
                "device_settings_missing",
                "internal_error",
            ),
        ),
        (
            30,
            None,
            2,
            2.0,
            10,
            3,
            (
                "device_authentication_failed",
                "device_identity_mismatch",
                "device_platform_mismatch",
                "configuration_rejected",
                "artifact_mismatch",
                "internal_error",
            ),
        ),
        (
            15,
            90,
            2,
            1.5,
            5,
            12,
            (
                "device_authentication_failed",
                "device_state_invalid",
                "validation_failed",
                "internal_error",
            ),
        ),
        (30, None, 1, 2.0, 10, 5, ()),
    )
    for item, (
        start,
        schedule,
        initial,
        coefficient,
        maximum,
        attempts,
        non_retryable,
    ) in zip(
        scheduled, expected, strict=True
    ):
        assert item.start_to_close_timeout == _duration(start)
        if schedule is not None:
            assert item.schedule_to_close_timeout == _duration(schedule)
        else:
            # The Temporal test server may materialize the workflow execution
            # timeout when schedule-to-close is omitted by the SDK.
            assert item.schedule_to_close_timeout in (Duration(), _duration(600))
        assert item.retry_policy.initial_interval == _duration(initial)
        assert item.retry_policy.backoff_coefficient == coefficient
        assert item.retry_policy.maximum_interval == _duration(maximum)
        assert item.retry_policy.maximum_attempts == attempts
        assert tuple(item.retry_policy.non_retryable_error_types) == non_retryable

    event_names = [
        event.event_type
        for event in history.events
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    ]
    assert len(event_names) == 4
    assert "network.render.completed" not in result.model_dump_json()
    assert "network.render.failed" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_transient_deploy_retry_reuses_prepared_artifact_without_rerender() -> None:
    counts = {"prepare": 0, "deploy": 0, "validate": 0, "publish": 0}
    prepared = _prepared()

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        assert value == prepared
        if counts["deploy"] < 3:
            raise ApplicationError(
                "device is temporarily unavailable",
                type="device_unavailable",
            )
        return _deployment_result(value)

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        return _validation_result(value)

    @activity.defn(name="publish_render_result")
    async def publish(_: DeploymentCompleted | DeploymentFailed) -> None:
        counts["publish"] += 1

    request = _deployment_request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-deploy-retry",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=deployment_workflow_id_for(request.event_id),
                task_queue="deployment-workflow-deploy-retry",
            )

    assert counts == {"prepare": 1, "deploy": 3, "validate": 1, "publish": 1}
    assert isinstance(result, DeploymentCompleted)
    assert result.artifact_sha256 == DIGEST


@pytest.mark.asyncio
async def test_validation_retry_does_not_reprepare_or_redeploy() -> None:
    counts = {"prepare": 0, "deploy": 0, "validate": 0, "publish": 0}
    prepared = _prepared()

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        return _deployment_result(value)

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        if counts["validate"] < 3:
            raise ApplicationError(
                "device state has not converged",
                type="validation_not_converged",
            )
        return _validation_result(value)

    @activity.defn(name="publish_render_result")
    async def publish(_: DeploymentCompleted | DeploymentFailed) -> None:
        counts["publish"] += 1

    request = _deployment_request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-validation-retry",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=deployment_workflow_id_for(request.event_id),
                task_queue="deployment-workflow-validation-retry",
            )

    assert counts == {"prepare": 1, "deploy": 1, "validate": 3, "publish": 1}
    assert isinstance(result, DeploymentCompleted)


@pytest.mark.asyncio
async def test_publication_retry_reuses_stable_outcome_without_prior_activities() -> None:
    counts = {"prepare": 0, "deploy": 0, "validate": 0}
    published_payloads: list[str] = []
    published_ids: list[UUID] = []
    prepared = _prepared()

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        return _deployment_result(value)

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        return _validation_result(value)

    @activity.defn(name="publish_render_result")
    async def publish(value: DeploymentCompleted | DeploymentFailed) -> None:
        published_payloads.append(value.model_dump_json())
        published_ids.append(value.event_id)
        if len(published_payloads) < 3:
            raise ApplicationError("result broker is temporarily unavailable")

    request = _deployment_request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-publication-retry",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=deployment_workflow_id_for(request.event_id),
                task_queue="deployment-workflow-publication-retry",
            )

    assert counts == {"prepare": 1, "deploy": 1, "validate": 1}
    assert len(published_payloads) == 3
    assert published_payloads == [result.model_dump_json()] * 3
    assert published_ids == [result.event_id] * 3


@pytest.mark.parametrize(
    ("exhausted_stage", "expected_counts", "failure_type"),
    [
        ("deploy", {"prepare": 1, "deploy": 3, "validate": 0, "publish": 1}, "device_unavailable"),
        (
            "validate",
            {"prepare": 1, "deploy": 1, "validate": 12, "publish": 1},
            "validation_not_converged",
        ),
    ],
)
@pytest.mark.asyncio
async def test_transient_recovery_exhaustion_is_bounded_at_its_activity_barrier(
    exhausted_stage: str,
    expected_counts: dict[str, int],
    failure_type: str,
) -> None:
    counts = {"prepare": 0, "deploy": 0, "validate": 0, "publish": 0}
    published: list[DeploymentCompleted | DeploymentFailed] = []
    prepared = _prepared()

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        if exhausted_stage == "deploy":
            raise ApplicationError(
                "device is temporarily unavailable",
                type="device_unavailable",
            )
        return _deployment_result(value)

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        if exhausted_stage == "validate":
            raise ApplicationError(
                "device state has not converged",
                type="validation_not_converged",
            )
        return _validation_result(value)

    @activity.defn(name="publish_render_result")
    async def publish(value: DeploymentCompleted | DeploymentFailed) -> None:
        counts["publish"] += 1
        published.append(value)

    request = _deployment_request()
    task_queue = f"deployment-workflow-{exhausted_stage}-exhaustion"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=deployment_workflow_id_for(request.event_id),
                task_queue=task_queue,
            )

    assert counts == expected_counts
    assert isinstance(result, DeploymentFailed)
    assert result.failure_stage == exhausted_stage
    assert result.error_type == failure_type
    assert published == [result]


@pytest.mark.asyncio
async def test_every_stable_failure_category_has_stage_metadata_and_retry_behavior() -> None:
    categories = {
        "prepare": (
            "nautobot_unavailable",
            "nautobot_rejected",
            "intent_invalid",
            "unsupported_platform",
            "management_address_invalid",
            "artifact_unavailable",
            "artifact_invalid",
            "artifact_mismatch",
            "device_settings_missing",
        ),
        "deploy": (
            "device_unavailable",
            "device_authentication_failed",
            "device_identity_mismatch",
            "device_platform_mismatch",
            "configuration_rejected",
            "artifact_mismatch",
            "internal_error",
        ),
        "validate": (
            "device_unavailable",
            "device_authentication_failed",
            "device_state_invalid",
            "validation_not_converged",
            "validation_failed",
            "internal_error",
        ),
    }
    retryable = {
        ("prepare", "nautobot_unavailable"): 3,
        ("prepare", "artifact_unavailable"): 3,
        ("deploy", "device_unavailable"): 3,
        ("validate", "device_unavailable"): 12,
        ("validate", "validation_not_converged"): 12,
    }
    current = {"stage": "", "category": ""}
    counts = {"prepare": 0, "deploy": 0, "validate": 0, "publish": 0}
    published: list[DeploymentFailed] = []
    prepared = _prepared()

    def fail_if_current(stage: str) -> None:
        if current["stage"] == stage:
            raise ApplicationError(
                f"safe {current['category']} failure",
                type=current["category"],
            )

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        fail_if_current("prepare")
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        fail_if_current("deploy")
        return _deployment_result(value)

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        fail_if_current("validate")
        return _validation_result(value)

    @activity.defn(name="publish_render_result")
    async def publish(value: DeploymentCompleted | DeploymentFailed) -> None:
        counts["publish"] += 1
        assert isinstance(value, DeploymentFailed)
        published.append(value)

    task_queue = "deployment-workflow-failure-category-matrix"
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue=task_queue,
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            case_number = 0
            for stage, stage_categories in categories.items():
                for category in stage_categories:
                    case_number += 1
                    current.update(stage=stage, category=category)
                    counts.update(prepare=0, deploy=0, validate=0, publish=0)
                    published.clear()
                    request = DeployDeviceConfigRequest(
                        operation="deploy",
                        event_id=UUID(int=case_number),
                        correlation_id=CORRELATION_ID,
                        device_name="f004-leaf01",
                    )
                    result = await environment.client.execute_workflow(
                        RenderDeviceConfigWorkflow.run,
                        request,
                        id=deployment_workflow_id_for(request.event_id),
                        task_queue=task_queue,
                    )

                    stage_attempts = retryable.get((stage, category), 1)
                    expected_counts = {
                        "prepare": stage_attempts if stage == "prepare" else 1,
                        "deploy": (
                            stage_attempts
                            if stage == "deploy"
                            else int(stage == "validate")
                        ),
                        "validate": stage_attempts if stage == "validate" else 0,
                        "publish": 1,
                    }
                    assert counts == expected_counts, (stage, category)
                    assert isinstance(result, DeploymentFailed)
                    assert published == [result]
                    assert result.failure_stage == stage
                    assert result.error_type == category
                    assert result.error_message == f"safe {category} failure"
                    assert result.correlation_id == request.correlation_id
                    assert result.device_name == request.device_name
                    assert result.workflow_id == deployment_workflow_id_for(
                        request.event_id
                    )
                    assert result.event_id.version == 4
                    assert result.failed_at.utcoffset() == timedelta(0)
                    if stage == "prepare":
                        assert result.artifact_sha256 is None
                        assert result.artifact_bytes is None
                        assert result.deployed_at is None
                    elif stage == "deploy":
                        assert result.artifact_sha256 == DIGEST
                        assert result.artifact_bytes == 1248
                        assert result.deployed_at is None
                    else:
                        assert result.artifact_sha256 == DIGEST
                        assert result.artifact_bytes == 1248
                        assert result.deployed_at == DEPLOYED_AT


@pytest.mark.asyncio
async def test_final_validation_mismatch_publishes_one_safe_failure_without_retry() -> None:
    counts = {"prepare": 0, "deploy": 0, "validate": 0, "publish": 0}
    published: list[DeploymentFailed] = []
    prepared = _prepared()

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        return prepared

    @activity.defn(name="deploy_device_artifact")
    async def deploy(value: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        return _deployment_result(value)

    @activity.defn(name="validate_device_state")
    async def validate(value: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        return DeviceValidationResult(
            device_name=value.target.device_name,
            status="failed",
            checks=(
                ValidationCheck(
                    name="routing.neighbor.192.0.2.0.session",
                    status="failed",
                    expected="established",
                    observed="idle",
                    message="BGP session is not established",
                ),
            ),
            validated_at=datetime(2026, 9, 10, 18, 1, 12, tzinfo=timezone.utc),
        )

    @activity.defn(name="publish_render_result")
    async def publish(value: DeploymentCompleted | DeploymentFailed) -> None:
        counts["publish"] += 1
        assert isinstance(value, DeploymentFailed)
        published.append(value)

    request = _deployment_request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-final-mismatch",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=deployment_workflow_id_for(request.event_id),
                task_queue="deployment-workflow-final-mismatch",
            )

    assert counts == {"prepare": 1, "deploy": 1, "validate": 1, "publish": 1}
    assert isinstance(result, DeploymentFailed)
    assert published == [result]
    assert result.failure_stage == "validate"
    assert result.error_type == "validation_failed"
    assert result.error_message == "device state did not match intended invariants"
    assert result.artifact_sha256 == DIGEST
    assert result.artifact_bytes == 1248
    assert result.deployed_at == DEPLOYED_AT
    serialized = result.model_dump_json()
    assert "routing.neighbor" not in serialized
    assert "BGP session" not in serialized
    assert "idle" not in serialized


@pytest.mark.asyncio
async def test_failure_publication_exhaustion_is_visible_with_one_stable_outcome() -> None:
    counts = {"prepare": 0, "deploy": 0, "validate": 0, "publish": 0}
    published_payloads: list[str] = []
    published_ids: list[UUID] = []

    @activity.defn(name="prepare_device_deployment")
    async def prepare(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        counts["prepare"] += 1
        raise ApplicationError(
            "deployment settings are not configured",
            type="device_settings_missing",
        )

    @activity.defn(name="deploy_device_artifact")
    async def deploy(_: PreparedDeployment) -> DeploymentResult:
        counts["deploy"] += 1
        raise AssertionError("deployment must not run after preparation failure")

    @activity.defn(name="validate_device_state")
    async def validate(_: PreparedDeployment) -> DeviceValidationResult:
        counts["validate"] += 1
        raise AssertionError("validation must not run after preparation failure")

    @activity.defn(name="publish_render_result")
    async def publish(value: DeploymentCompleted | DeploymentFailed) -> None:
        counts["publish"] += 1
        assert isinstance(value, DeploymentFailed)
        published_payloads.append(value.model_dump_json())
        published_ids.append(value.event_id)
        raise ApplicationError("result broker is temporarily unavailable")

    request = _deployment_request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-failure-publication-exhaustion",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[prepare, deploy, validate, publish],
        ):
            with pytest.raises(WorkflowFailureError) as failure:
                await environment.client.execute_workflow(
                    RenderDeviceConfigWorkflow.run,
                    request,
                    id=deployment_workflow_id_for(request.event_id),
                    task_queue="deployment-workflow-failure-publication-exhaustion",
                )

    assert isinstance(failure.value.__cause__, ActivityError)
    assert counts == {"prepare": 1, "deploy": 0, "validate": 0, "publish": 5}
    assert len(published_payloads) == 5
    assert published_payloads == [published_payloads[0]] * 5
    assert published_ids == [published_ids[0]] * 5
    assert "device_settings_missing" in published_payloads[0]
    assert "result broker is temporarily unavailable" not in published_payloads[0]


@pytest.mark.asyncio
async def test_existing_render_branch_sequence_and_policies_remain_unchanged() -> None:
    calls: list[tuple[str, object]] = []

    @activity.defn(name="render_device_artifact")
    async def render(value: RenderDeviceConfigRequest) -> ArtifactMetadata:
        calls.append(("render", value))
        return ArtifactMetadata(
            device_name=value.device_name,
            artifact_path="artifacts/configs/leaf01.cfg",
        )

    @activity.defn(name="publish_render_result")
    async def publish(value: RenderCompleted | RenderFailed) -> None:
        calls.append(("publish", value))

    request = RenderDeviceConfigRequest(
        event_id=UUID("77ee1844-cd3a-4c45-8de7-3dd76fc7da2d"),
        correlation_id=UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80"),
        device_name="leaf01",
    )
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="deployment-workflow-render-regression",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            handle = await environment.client.start_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=workflow_id_for(request.event_id),
                task_queue="deployment-workflow-render-regression",
            )
            result = await handle.result()
            history = await handle.fetch_history()

    assert [name for name, _ in calls] == ["render", "publish"]
    assert isinstance(result, RenderCompleted)
    assert result.workflow_id == workflow_id_for(request.event_id)
    assert result.artifact_path == "artifacts/configs/leaf01.cfg"
    assert calls[1][1] == result

    render, publish = _scheduled_activities(history)
    assert render.activity_type.name == "render_device_artifact"
    assert render.start_to_close_timeout == _duration(60)
    assert render.retry_policy.initial_interval == _duration(1)
    assert render.retry_policy.backoff_coefficient == 2.0
    assert render.retry_policy.maximum_interval == _duration(10)
    assert render.retry_policy.maximum_attempts == 3
    assert tuple(render.retry_policy.non_retryable_error_types) == (
        "intent_invalid",
        "nautobot_rejected",
        "unsupported_platform",
        "render_invalid",
        "internal_error",
    )
    assert publish.activity_type.name == "publish_render_result"
    assert publish.start_to_close_timeout == _duration(30)
    assert publish.retry_policy.initial_interval == _duration(1)
    assert publish.retry_policy.backoff_coefficient == 2.0
    assert publish.retry_policy.maximum_interval == _duration(10)
    assert publish.retry_policy.maximum_attempts == 5
    assert tuple(publish.retry_policy.non_retryable_error_types) == ()
