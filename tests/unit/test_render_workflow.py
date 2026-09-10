from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from network_automation.events.models import (
    ArtifactMetadata,
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
    workflow_id_for,
)
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow


def request() -> RenderDeviceConfigRequest:
    return RenderDeviceConfigRequest(
        event_id=UUID("77ee1844-cd3a-4c45-8de7-3dd76fc7da2d"),
        correlation_id=UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80"),
        device_name="leaf01",
    )


@pytest.mark.asyncio
async def test_success_renders_before_publishing_correlated_completion() -> None:
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

    value = request()
    workflow_id = workflow_id_for(value.event_id)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="workflow-success",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                value,
                id=workflow_id,
                task_queue="workflow-success",
            )

    assert [name for name, _ in calls] == ["render", "publish"]
    assert isinstance(result, RenderCompleted)
    assert result.correlation_id == value.correlation_id
    assert result.device_name == value.device_name
    assert result.workflow_id == workflow_id
    assert result.artifact_path == "artifacts/configs/leaf01.cfg"
    assert result.completed_at.utcoffset() == timedelta(0)
    assert result.event_id != value.event_id
    assert calls[1][1] == result


@pytest.mark.asyncio
async def test_transient_render_retries_are_bounded_before_publication() -> None:
    attempts = 0
    published: list[RenderCompleted | RenderFailed] = []

    @activity.defn(name="render_device_artifact")
    async def render(value: RenderDeviceConfigRequest) -> ArtifactMetadata:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ApplicationError(
                "Nautobot is temporarily unavailable",
                type="nautobot_unavailable",
            )
        return ArtifactMetadata(
            device_name=value.device_name,
            artifact_path="artifacts/configs/leaf01.cfg",
        )

    @activity.defn(name="publish_render_result")
    async def publish(value: RenderCompleted | RenderFailed) -> None:
        published.append(value)

    value = request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="workflow-render-retry",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                value,
                id=workflow_id_for(value.event_id),
                task_queue="workflow-render-retry",
            )

    assert attempts == 3
    assert published == [result]
    assert isinstance(result, RenderCompleted)


@pytest.mark.asyncio
async def test_publication_retry_keeps_result_identity_without_rerendering() -> None:
    render_count = 0
    publish_payloads: list[str] = []
    publish_ids: list[UUID] = []

    @activity.defn(name="render_device_artifact")
    async def render(value: RenderDeviceConfigRequest) -> ArtifactMetadata:
        nonlocal render_count
        render_count += 1
        return ArtifactMetadata(
            device_name=value.device_name,
            artifact_path="artifacts/configs/leaf01.cfg",
        )

    @activity.defn(name="publish_render_result")
    async def publish(value: RenderCompleted | RenderFailed) -> None:
        publish_payloads.append(value.model_dump_json())
        publish_ids.append(value.event_id)
        if len(publish_payloads) == 1:
            raise ApplicationError("result broker is temporarily unavailable")

    value = request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="workflow-publish-retry",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                value,
                id=workflow_id_for(value.event_id),
                task_queue="workflow-publish-retry",
            )

    assert render_count == 1
    assert len(publish_payloads) == 2
    assert publish_payloads[0] == publish_payloads[1] == result.model_dump_json()
    assert publish_ids == [result.event_id, result.event_id]


@pytest.mark.asyncio
async def test_permanent_render_failures_publish_safe_correlated_outcomes() -> None:
    categories = (
        "intent_invalid",
        "nautobot_rejected",
        "unsupported_platform",
        "render_invalid",
        "internal_error",
    )
    attempts: defaultdict[str, int] = defaultdict(int)
    published: list[RenderCompleted | RenderFailed] = []

    @activity.defn(name="render_device_artifact")
    async def render(value: RenderDeviceConfigRequest) -> ArtifactMetadata:
        attempts[value.device_name] += 1
        raise ApplicationError(
            "render request cannot be completed safely",
            type=value.device_name,
            non_retryable=True,
        )

    @activity.defn(name="publish_render_result")
    async def publish(value: RenderCompleted | RenderFailed) -> None:
        published.append(value)

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="workflow-permanent-failure",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            results: list[Any] = []
            for category in categories:
                value = RenderDeviceConfigRequest(
                    event_id=uuid4(),
                    correlation_id=uuid4(),
                    device_name=category,
                )
                result = await environment.client.execute_workflow(
                    RenderDeviceConfigWorkflow.run,
                    value,
                    id=workflow_id_for(value.event_id),
                    task_queue="workflow-permanent-failure",
                )
                results.append((value, result))

    assert len(published) == len(categories)
    for value, result in results:
        assert isinstance(result, RenderFailed)
        assert attempts[value.device_name] == 1
        assert result.error_type == value.device_name
        assert result.error_message == "render request cannot be completed safely"
        assert result.correlation_id == value.correlation_id
        assert result.workflow_id == workflow_id_for(value.event_id)
        assert result.failed_at.utcoffset() == timedelta(0)
        assert "secret" not in result.model_dump_json().lower()
        assert published.count(result) == 1


@pytest.mark.asyncio
async def test_exhausted_publication_fails_visibly_without_rerendering() -> None:
    render_count = 0
    publish_count = 0

    @activity.defn(name="render_device_artifact")
    async def render(value: RenderDeviceConfigRequest) -> ArtifactMetadata:
        nonlocal render_count
        render_count += 1
        return ArtifactMetadata(
            device_name=value.device_name,
            artifact_path="artifacts/configs/leaf01.cfg",
        )

    @activity.defn(name="publish_render_result")
    async def publish(_: RenderCompleted | RenderFailed) -> None:
        nonlocal publish_count
        publish_count += 1
        raise ApplicationError("result broker is temporarily unavailable")

    value = request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="workflow-publish-exhausted",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            with pytest.raises(WorkflowFailureError):
                await environment.client.execute_workflow(
                    RenderDeviceConfigWorkflow.run,
                    value,
                    id=workflow_id_for(value.event_id),
                    task_queue="workflow-publish-exhausted",
                )

    assert render_count == 1
    assert publish_count == 5


@pytest.mark.asyncio
async def test_unknown_render_failure_becomes_safe_internal_failure() -> None:
    published: list[RenderCompleted | RenderFailed] = []

    @activity.defn(name="render_device_artifact")
    async def render(_: RenderDeviceConfigRequest) -> ArtifactMetadata:
        raise ApplicationError(
            "raw traceback included super-secret",
            type="unexpected_error",
            non_retryable=True,
        )

    @activity.defn(name="publish_render_result")
    async def publish(value: RenderCompleted | RenderFailed) -> None:
        published.append(value)

    value = request()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as environment:
        async with Worker(
            environment.client,
            task_queue="workflow-unknown-failure",
            workflows=[RenderDeviceConfigWorkflow],
            activities=[render, publish],
        ):
            result = await environment.client.execute_workflow(
                RenderDeviceConfigWorkflow.run,
                value,
                id=workflow_id_for(value.event_id),
                task_queue="workflow-unknown-failure",
            )

    assert isinstance(result, RenderFailed)
    assert result.error_type == "internal_error"
    assert result.error_message == "render activity did not complete"
    assert "super-secret" not in result.model_dump_json()
    assert published == [result]
