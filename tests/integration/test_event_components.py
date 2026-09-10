from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from confluent_kafka import Consumer
from confluent_kafka.admin import AdminClient, NewTopic
from temporalio import activity
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from network_automation.events.models import (
    ArtifactMetadata,
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
    RenderRequested,
    workflow_id_for,
)
from network_automation.events.producer import publish_event
from network_automation.settings import LabSettings
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow

pytestmark = pytest.mark.integration


def test_real_kafka_round_trip_for_all_event_contracts() -> None:
    settings = LabSettings()
    suffix = uuid4().hex
    topics = [f"feature003-{kind}-{suffix}" for kind in ("request", "completed", "failed")]
    isolated = settings.model_copy(
        update={
            "render_request_topic": topics[0],
            "render_completed_topic": topics[1],
            "render_failed_topic": topics[2],
        }
    )
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    futures = admin.create_topics([NewTopic(topic, 1, 1) for topic in topics])
    for future in futures.values():
        future.result(settings.probe_timeout_seconds)
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": f"feature003-components-{suffix}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe(topics)
    request_id = uuid4()
    correlation_id = uuid4()
    now = datetime.now(timezone.utc)
    events = (
        RenderRequested(
            event_type="network.render.requested",
            event_version=1,
            event_id=request_id,
            correlation_id=correlation_id,
            device_name="leaf01",
            requested_at=now,
            source="integration",
        ),
        RenderCompleted(
            event_type="network.render.completed",
            event_version=1,
            event_id=uuid4(),
            correlation_id=correlation_id,
            device_name="leaf01",
            workflow_id=workflow_id_for(request_id),
            artifact_path="artifacts/configs/leaf01.cfg",
            completed_at=now,
        ),
        RenderFailed(
            event_type="network.render.failed",
            event_version=1,
            event_id=uuid4(),
            correlation_id=correlation_id,
            device_name="leaf01",
            workflow_id=workflow_id_for(request_id),
            error_type="intent_invalid",
            error_message="device intent validation failed",
            failed_at=now,
        ),
    )
    try:
        for event in events:
            publish_event(event, isolated)
        received: dict[str, tuple[bytes, bytes]] = {}
        while len(received) < 3:
            message = consumer.poll(settings.probe_timeout_seconds)
            assert message is not None and message.error() is None
            received[message.topic()] = (message.key(), message.value())
        for topic, event in zip(topics, events, strict=True):
            key, value = received[topic]
            assert key.decode() == str(event.event_id)
            assert value == event.model_dump_json().encode()
    finally:
        consumer.close()
        deleted = admin.delete_topics(topics)
        for future in deleted.values():
            future.result(settings.probe_timeout_seconds)


@pytest.mark.asyncio
async def test_real_temporal_worker_executes_the_single_workflow() -> None:
    settings = LabSettings()
    task_queue = f"feature003-components-{uuid4().hex}"

    @activity.defn(name="render_device_artifact")
    async def render(request: RenderDeviceConfigRequest) -> ArtifactMetadata:
        return ArtifactMetadata(
            device_name=request.device_name,
            artifact_path=f"artifacts/configs/{request.device_name}.cfg",
        )

    @activity.defn(name="publish_render_result")
    async def publish(_: RenderCompleted | RenderFailed) -> None:
        return None

    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    request = RenderDeviceConfigRequest(
        event_id=uuid4(), correlation_id=uuid4(), device_name="component-leaf"
    )
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[RenderDeviceConfigWorkflow],
        activities=[render, publish],
    ):
        handle = await client.start_workflow(
            RenderDeviceConfigWorkflow.run,
            request,
            id=workflow_id_for(request.event_id),
            task_queue=task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        result = await handle.result()
    assert isinstance(result, RenderCompleted)
    assert result.correlation_id == request.correlation_id
    assert result.workflow_id == workflow_id_for(request.event_id)
