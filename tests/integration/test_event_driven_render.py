from __future__ import annotations

import asyncio
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from confluent_kafka import Consumer, KafkaError, Producer, TopicPartition
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError

from network_automation.cli.render import render_device
from network_automation.events.models import (
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
    RenderRequested,
    workflow_id_for,
)
from network_automation.events.producer import publish_event
from network_automation.settings import LabSettings
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow
from tests.integration.support.nautobot_fixture import FixtureApi, create_render_device

pytestmark = pytest.mark.integration


def _request(device_name: str) -> RenderRequested:
    return RenderRequested(
        event_type="network.render.requested",
        event_version=1,
        event_id=uuid4(),
        correlation_id=uuid4(),
        device_name=device_name,
        requested_at=datetime.now(timezone.utc),
        source="integration",
    )


def _result_consumer(settings: LabSettings) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": f"feature003-results-{uuid4().hex}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "topic.metadata.refresh.interval.ms": 1000,
        }
    )
    consumer.subscribe([settings.render_completed_topic, settings.render_failed_topic])
    return consumer


def _wait_for_result(
    consumer: Consumer,
    correlation_id: UUID,
    *,
    timeout: float = 120,
) -> RenderCompleted | RenderFailed:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = consumer.poll(min(2, deadline - time.monotonic()))
        if message is None:
            continue
        error = message.error()
        if error is not None and error.code() in {
            KafkaError.UNKNOWN_TOPIC_OR_PART,
            KafkaError._PARTITION_EOF,
        }:
            continue
        assert error is None
        payload = json.loads(message.value())
        if payload.get("correlation_id") != str(correlation_id):
            continue
        if payload.get("event_type") == "network.render.completed":
            return RenderCompleted.model_validate(payload)
        if payload.get("event_type") == "network.render.failed":
            return RenderFailed.model_validate(payload)
    pytest.fail(f"no result received for correlation ID {correlation_id}")


def _compose(settings: LabSettings, *arguments: str) -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            settings.compose_project,
            "--profile",
            "automation",
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _compose_logs(settings: LabSettings, service: str) -> str:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            settings.compose_project,
            "--profile",
            "automation",
            "logs",
            "--no-color",
            service,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout


def _require_automation_services(settings: LabSettings) -> None:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            settings.compose_project,
            "--profile",
            "automation",
            "ps",
            "--format",
            "json",
            "automation-worker",
            "event-consumer",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = completed.stdout.strip()
    try:
        parsed = json.loads(output)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    by_service = {row["Service"]: row for row in rows}
    for service in ("automation-worker", "event-consumer"):
        assert service in by_service, f"required service {service} is absent"
        assert by_service[service]["State"].lower() == "running"
        assert by_service[service]["Health"].lower() == "healthy"


async def _wait_until_running(client: Client, workflow_id: str) -> None:
    deadline = asyncio.get_running_loop().time() + 30
    while asyncio.get_running_loop().time() < deadline:
        try:
            description = await client.get_workflow_handle(workflow_id).describe()
        except RPCError:
            await asyncio.sleep(0.5)
            continue
        if description.status == WorkflowExecutionStatus.RUNNING:
            return
        await asyncio.sleep(0.5)
    pytest.fail(f"workflow {workflow_id} did not become pending/running")


@pytest.mark.asyncio
async def test_event_driven_render_duplicate_poison_failure_and_restarts(
    tmp_path: Path,
) -> None:
    settings = LabSettings()
    _require_automation_services(settings)
    fixture = FixtureApi(settings)
    suffix = uuid4().hex[:8]
    valid_device = f"feature003-leaf-{suffix}"
    invalid_device = f"feature003-bad-{suffix}"
    artifact_paths = {
        Path("artifacts/configs") / f"{valid_device}.cfg",
        Path("artifacts/configs") / f"{invalid_device}.cfg",
    }
    results = _result_consumer(settings)
    worker_stopped = False
    consumer_stopped = False
    try:
        create_render_device(
            fixture,
            marker=f"feature003-valid-{suffix}",
            device_name=valid_device,
        )
        create_render_device(
            fixture,
            marker=f"feature003-invalid-{suffix}",
            device_name=invalid_device,
            network_driver="unsupported_os",
        )

        poison_id = uuid4()
        secret_marker = "credential=must-not-be-logged"
        poison_payload = {
            "event_type": "network.render.requested",
            "event_version": 1,
            "event_id": str(poison_id),
            "correlation_id": str(uuid4()),
            "device_name": valid_device,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "source": "integration",
            "unexpected": secret_marker,
        }
        producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        poison_delivery: list[object] = []
        producer.produce(
            settings.render_request_topic,
            key=str(poison_id),
            value=json.dumps(poison_payload).encode(),
            callback=lambda error, message: poison_delivery.append(error or message),
        )
        assert producer.flush(settings.probe_timeout_seconds) == 0
        poison_message = poison_delivery[0]
        assert not isinstance(poison_message, KafkaError)

        valid = _request(valid_device)
        publish_event(valid, settings)
        publish_event(valid, settings)
        completed = _wait_for_result(results, valid.correlation_id)
        assert isinstance(completed, RenderCompleted)
        assert completed.workflow_id == workflow_id_for(valid.event_id)
        artifact = Path(completed.artifact_path)
        direct = render_device(valid_device, tmp_path)
        assert artifact.read_bytes() == direct.read_bytes()

        temporal = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            data_converter=pydantic_data_converter,
        )
        with pytest.raises(RPCError):
            await temporal.get_workflow_handle(workflow_id_for(poison_id)).describe()
        committed = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.render_consumer_group,
                "enable.auto.commit": False,
            }
        )
        try:
            positions = committed.committed(
                [TopicPartition(poison_message.topic(), poison_message.partition())],
                timeout=settings.probe_timeout_seconds,
            )
            assert positions[0].offset > poison_message.offset()
        finally:
            committed.close()
        consumer_logs = _compose_logs(settings, "event-consumer")
        assert str(poison_id) in consumer_logs
        assert "category=validation_error" in consumer_logs
        assert secret_marker not in consumer_logs
        assert json.dumps(poison_payload) not in consumer_logs
        duplicate_input = RenderDeviceConfigRequest(
            event_id=valid.event_id,
            correlation_id=valid.correlation_id,
            device_name=valid.device_name,
        )
        with pytest.raises(WorkflowAlreadyStartedError):
            await temporal.start_workflow(
                RenderDeviceConfigWorkflow.run,
                duplicate_input,
                id=workflow_id_for(valid.event_id),
                task_queue=settings.temporal_task_queue,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )

        invalid = _request(invalid_device)
        publish_event(invalid, settings)
        failed = _wait_for_result(results, invalid.correlation_id)
        assert isinstance(failed, RenderFailed)
        assert failed.error_type == "unsupported_platform"
        assert "unsupported_os" not in failed.error_message

        _compose(settings, "stop", "automation-worker")
        worker_stopped = True
        pending = _request(valid_device)
        publish_event(pending, settings)
        await _wait_until_running(temporal, workflow_id_for(pending.event_id))
        _compose(settings, "up", "-d", "--wait", "automation-worker")
        worker_stopped = False
        recovered = _wait_for_result(results, pending.correlation_id)
        assert recovered.workflow_id == workflow_id_for(pending.event_id)

        _compose(settings, "stop", "event-consumer")
        consumer_stopped = True
        redelivered = _request(valid_device)
        redelivery_positions: list[object] = []
        producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        producer.produce(
            settings.render_request_topic,
            key=str(redelivered.event_id),
            value=redelivered.model_dump_json().encode(),
            callback=lambda error, message: redelivery_positions.append(error or message),
        )
        assert producer.flush(settings.probe_timeout_seconds) == 0
        delivered = redelivery_positions[0]
        assert not isinstance(delivered, KafkaError)
        interrupted = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": settings.render_consumer_group,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        try:
            interrupted.assign(
                [TopicPartition(delivered.topic(), delivered.partition(), delivered.offset())]
            )
            message = interrupted.poll(settings.probe_timeout_seconds)
            assert message is not None and message.error() is None
            assert json.loads(message.value())["event_id"] == str(redelivered.event_id)
        finally:
            interrupted.close()
        with pytest.raises(RPCError):
            await temporal.get_workflow_handle(
                workflow_id_for(redelivered.event_id)
            ).describe()
        _compose(settings, "up", "-d", "--wait", "event-consumer")
        consumer_stopped = False
        after_restart = _wait_for_result(results, redelivered.correlation_id)
        assert after_restart.workflow_id == workflow_id_for(redelivered.event_id)
    finally:
        if worker_stopped:
            _compose(settings, "up", "-d", "--wait", "automation-worker")
        if consumer_stopped:
            _compose(settings, "up", "-d", "--wait", "event-consumer")
        results.close()
        for path in artifact_paths:
            path.unlink(missing_ok=True)
        try:
            fixture.cleanup()
        finally:
            fixture.close()
