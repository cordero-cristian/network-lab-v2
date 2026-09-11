"""Kafka-to-Temporal bridge for validated automation requests."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from confluent_kafka import Consumer, KafkaError, TopicPartition
from pydantic import ValidationError
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import WorkflowAlreadyStartedError

from network_automation.events.models import (
    DeploymentRequested,
    DeployDeviceConfigRequest,
    RenderDeviceConfigRequest,
    RenderRequested,
    deployment_workflow_id_for,
    workflow_id_for,
)
from network_automation.settings import LabSettings
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow

LOGGER = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_SECONDS = 10.0
READY_PATH = Path("/tmp/network-event-consumer.ready")
HEARTBEAT_PATH = Path("/tmp/network-event-consumer.heartbeat")


def _position(message: Any) -> TopicPartition:
    return TopicPartition(message.topic(), message.partition(), message.offset())


def _parse_event_id(payload: bytes) -> str | None:
    try:
        value = json.loads(payload)
        candidate = value.get("event_id") if isinstance(value, dict) else None
        return str(UUID(candidate)) if isinstance(candidate, str) else None
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return None


def _commit_or_seek(message: Any, consumer: Any) -> bool:
    try:
        committed = consumer.commit(message=message, asynchronous=False)
        if any(partition.error is not None for partition in committed):
            raise RuntimeError("broker rejected offset commit")
    except Exception:
        consumer.seek(_position(message))
        LOGGER.warning(
            "Kafka offset commit failed; exact message will be retried "
            "topic=%s partition=%s offset=%s category=commit_error",
            message.topic(),
            message.partition(),
            message.offset(),
            extra={
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
                "category": "commit_error",
            },
        )
        return False
    return True


async def process_message(
    message: Any,
    consumer: Any,
    temporal_client: Any,
    settings: LabSettings | None = None,
) -> bool:
    render_topic = settings.render_request_topic if settings else "network.render.requested"
    deployment_topic = (
        settings.deployment_request_topic
        if settings
        else "network.deployment.requested"
    )
    try:
        if message.topic() == render_topic:
            event = RenderRequested.model_validate_json(message.value())
            request = RenderDeviceConfigRequest(
                event_id=event.event_id,
                correlation_id=event.correlation_id,
                device_name=event.device_name,
            )
            workflow_id = workflow_id_for(event.event_id)
        elif message.topic() == deployment_topic:
            event = DeploymentRequested.model_validate_json(message.value())
            request = DeployDeviceConfigRequest(
                operation="deploy",
                event_id=event.event_id,
                correlation_id=event.correlation_id,
                device_name=event.device_name,
            )
            workflow_id = deployment_workflow_id_for(event.event_id)
        else:
            raise ValueError("unexpected request topic")
    except (ValidationError, ValueError, TypeError):
        LOGGER.warning(
            "Rejected poison automation request topic=%s partition=%s offset=%s "
            "event_id=%s category=validation_error",
            message.topic(),
            message.partition(),
            message.offset(),
            _parse_event_id(message.value()),
            extra={
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
                "event_id": _parse_event_id(message.value()),
                "category": "validation_error",
            },
        )
        return _commit_or_seek(message, consumer)

    task_queue = settings.temporal_task_queue if settings else "network-automation"
    try:
        await temporal_client.start_workflow(
            RenderDeviceConfigWorkflow.run,
            request,
            id=workflow_id,
            task_queue=task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            execution_timeout=timedelta(minutes=10),
            rpc_timeout=timedelta(seconds=10),
        )
    except WorkflowAlreadyStartedError:
        pass
    except Exception:
        consumer.seek(_position(message))
        LOGGER.warning(
            "Temporal did not accept render request; exact message will be retried "
            "topic=%s partition=%s offset=%s event_id=%s correlation_id=%s "
            "workflow_id=%s device_name=%s category=workflow_start_error",
            message.topic(),
            message.partition(),
            message.offset(),
            event.event_id,
            event.correlation_id,
            workflow_id,
            event.device_name,
            extra={
                "topic": message.topic(),
                "partition": message.partition(),
                "offset": message.offset(),
                "event_id": str(event.event_id),
                "correlation_id": str(event.correlation_id),
                "workflow_id": workflow_id,
                "device_name": event.device_name,
                "category": "workflow_start_error",
            },
        )
        return False
    LOGGER.info(
        "Automation workflow accepted topic=%s partition=%s offset=%s event_type=%s "
        "event_id=%s correlation_id=%s workflow_id=%s device_name=%s",
        message.topic(),
        message.partition(),
        message.offset(),
        event.event_type,
        event.event_id,
        event.correlation_id,
        workflow_id,
        event.device_name,
        extra={
            "topic": message.topic(),
            "partition": message.partition(),
            "offset": message.offset(),
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "correlation_id": str(event.correlation_id),
            "workflow_id": workflow_id,
            "device_name": event.device_name,
        },
    )
    return _commit_or_seek(message, consumer)


async def run_consumer(
    settings: LabSettings,
    *,
    stop_event: asyncio.Event | None = None,
    ready_path: Path = READY_PATH,
    heartbeat_path: Path = HEARTBEAT_PATH,
) -> None:
    stop_event = stop_event or asyncio.Event()
    temporal_client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": settings.render_consumer_group,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe(
        [settings.render_request_topic, settings.deployment_request_topic]
    )
    ready = False
    next_broker_probe = 0.0
    try:
        while not stop_event.is_set():
            now = asyncio.get_running_loop().time()
            if now >= next_broker_probe:
                try:
                    consumer.list_topics(timeout=settings.probe_timeout_seconds)
                except Exception:
                    LOGGER.warning(
                        "Kafka metadata probe failed category=broker_unavailable",
                        extra={"category": "broker_unavailable"},
                    )
                    await asyncio.sleep(1)
                    continue
                ready_path.touch()
                heartbeat_path.touch()
                if not ready:
                    LOGGER.info(
                        "Event consumer ready topics=%s,%s group=%s",
                        settings.render_request_topic,
                        settings.deployment_request_topic,
                        settings.render_consumer_group,
                    )
                    ready = True
                next_broker_probe = now + HEARTBEAT_INTERVAL_SECONDS
            message = consumer.poll(1.0)
            if message is None:
                continue
            error = message.error()
            if error is not None:
                if error.code() in {KafkaError.UNKNOWN_TOPIC_OR_PART, KafkaError._PARTITION_EOF}:
                    continue
                LOGGER.warning(
                    "Kafka consumer poll failed category=poll_error code=%s",
                    error.code(),
                    extra={"category": "poll_error"},
                )
                continue
            await process_message(message, consumer, temporal_client, settings)
    finally:
        consumer.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    try:
        settings = LabSettings()
        stop_event = asyncio.Event()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signal_number, stop_event.set)
        loop.run_until_complete(run_consumer(settings, stop_event=stop_event))
    except Exception as exc:
        print(f"consumer startup failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    finally:
        if "loop" in locals():
            loop.close()
    return 0
