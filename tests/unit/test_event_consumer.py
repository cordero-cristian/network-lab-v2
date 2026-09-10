from __future__ import annotations

import ast
import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from confluent_kafka import TopicPartition
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

from network_automation.events import consumer as consumer_module
from network_automation.events.consumer import process_message
from network_automation.events.models import RenderDeviceConfigRequest
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow


EVENT_ID = UUID("77ee1844-cd3a-4c45-8de7-3dd76fc7da2d")
CORRELATION_ID = UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80")
WORKFLOW_ID = f"render-device-config:{EVENT_ID}"


class FakeMessage:
    def __init__(
        self,
        value: bytes,
        *,
        topic: str = "network.render.requested",
        partition: int = 2,
        offset: int = 41,
    ) -> None:
        self._value = value
        self._topic = topic
        self._partition = partition
        self._offset = offset

    def value(self) -> bytes:
        return self._value

    def topic(self) -> str:
        return self._topic

    def partition(self) -> int:
        return self._partition

    def offset(self) -> int:
        return self._offset


class FakeConsumer:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.commit_error = commit_error
        self.calls: list[tuple[str, object]] = []

    def commit(self, *, message: FakeMessage, asynchronous: bool) -> list[object]:
        self.calls.append(("commit", (message, asynchronous)))
        if self.commit_error is not None:
            raise self.commit_error
        return []

    def seek(self, partition: TopicPartition) -> None:
        self.calls.append(("seek", partition))


def request_bytes(**overrides: Any) -> bytes:
    payload: dict[str, object] = {
        "event_type": "network.render.requested",
        "event_version": 1,
        "event_id": str(EVENT_ID),
        "correlation_id": str(CORRELATION_ID),
        "device_name": "leaf01",
        "requested_at": "2026-09-09T18:00:00Z",
        "source": "cli",
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def assert_exact_seek(call: tuple[str, object], message: FakeMessage) -> None:
    name, position = call
    assert name == "seek"
    assert isinstance(position, TopicPartition)
    assert (position.topic, position.partition, position.offset) == (
        message.topic(),
        message.partition(),
        message.offset(),
    )


@pytest.mark.asyncio
async def test_valid_message_starts_exact_workflow_then_commits_synchronously() -> None:
    message = FakeMessage(request_bytes())
    consumer = FakeConsumer()
    temporal_client = AsyncMock()

    assert await process_message(message, consumer, temporal_client) is True

    temporal_client.start_workflow.assert_awaited_once_with(
        RenderDeviceConfigWorkflow.run,
        RenderDeviceConfigRequest(
            event_id=EVENT_ID,
            correlation_id=CORRELATION_ID,
            device_name="leaf01",
        ),
        id=WORKFLOW_ID,
        task_queue="network-automation",
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        execution_timeout=timedelta(minutes=10),
        rpc_timeout=timedelta(seconds=10),
    )
    assert consumer.calls == [("commit", (message, False))]


@pytest.mark.asyncio
async def test_retained_closed_workflow_is_accepted_and_committed() -> None:
    message = FakeMessage(request_bytes())
    consumer = FakeConsumer()
    temporal_client = AsyncMock()
    temporal_client.start_workflow.side_effect = WorkflowAlreadyStartedError(
        WORKFLOW_ID, "RenderDeviceConfigWorkflow", run_id="retained-run"
    )

    assert await process_message(message, consumer, temporal_client) is True
    assert consumer.calls == [("commit", (message, False))]


@pytest.mark.asyncio
async def test_start_error_seeks_exact_message_without_committing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = FakeMessage(request_bytes())
    consumer = FakeConsumer()
    temporal_client = AsyncMock()
    temporal_client.start_workflow.side_effect = RuntimeError(
        "Temporal unavailable with super-secret"
    )

    with caplog.at_level(logging.WARNING):
        assert await process_message(message, consumer, temporal_client) is False

    assert len(consumer.calls) == 1
    assert_exact_seek(consumer.calls[0], message)
    assert "super-secret" not in caplog.text


@pytest.mark.asyncio
async def test_valid_commit_error_seeks_exact_message_for_retry() -> None:
    message = FakeMessage(request_bytes())
    consumer = FakeConsumer(commit_error=RuntimeError("commit failed"))
    temporal_client = AsyncMock()

    assert await process_message(message, consumer, temporal_client) is False

    assert consumer.calls[0] == ("commit", (message, False))
    assert_exact_seek(consumer.calls[1], message)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xffnot-utf8",
        b"not-json",
        b"[]",
        request_bytes(event_type="network.render.completed"),
        request_bytes(event_version=2),
        request_bytes(unexpected="field"),
    ],
    ids=["non-utf8", "non-json", "non-object", "wrong-type", "wrong-version", "extra-field"],
)
@pytest.mark.asyncio
async def test_poison_message_never_starts_workflow_and_commits_synchronously(
    payload: bytes,
) -> None:
    message = FakeMessage(payload)
    consumer = FakeConsumer()
    temporal_client = AsyncMock()

    assert await process_message(message, consumer, temporal_client) is True

    temporal_client.start_workflow.assert_not_awaited()
    assert consumer.calls == [("commit", (message, False))]


@pytest.mark.asyncio
async def test_poison_log_has_safe_structured_context_without_payload_or_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = request_bytes(unexpected="super-secret")
    message = FakeMessage(payload, topic="requests.test", partition=7, offset=99)
    consumer = FakeConsumer()

    with caplog.at_level(logging.WARNING):
        assert await process_message(message, consumer, AsyncMock()) is True

    record = caplog.records[-1]
    assert record.topic == "requests.test"  # type: ignore[attr-defined]
    assert record.partition == 7  # type: ignore[attr-defined]
    assert record.offset == 99  # type: ignore[attr-defined]
    assert record.event_id == str(EVENT_ID)  # type: ignore[attr-defined]
    assert record.category == "validation_error"  # type: ignore[attr-defined]
    assert payload.decode() not in caplog.text
    assert "super-secret" not in caplog.text


@pytest.mark.asyncio
async def test_poison_commit_error_seeks_exact_message() -> None:
    message = FakeMessage(b"not-json")
    consumer = FakeConsumer(commit_error=RuntimeError("commit failed"))
    temporal_client = AsyncMock()

    assert await process_message(message, consumer, temporal_client) is False

    temporal_client.start_workflow.assert_not_awaited()
    assert consumer.calls[0] == ("commit", (message, False))
    assert_exact_seek(consumer.calls[1], message)


@pytest.mark.asyncio
async def test_poison_outcome_allows_the_next_valid_message_to_run() -> None:
    poison = FakeMessage(b"not-json", offset=41)
    valid = FakeMessage(request_bytes(), offset=42)
    consumer = FakeConsumer()
    temporal_client = AsyncMock()

    assert await process_message(poison, consumer, temporal_client) is True
    assert await process_message(valid, consumer, temporal_client) is True

    temporal_client.start_workflow.assert_awaited_once()
    assert consumer.calls == [
        ("commit", (poison, False)),
        ("commit", (valid, False)),
    ]


def test_consumer_does_not_depend_on_forbidden_automation_boundaries() -> None:
    tree = ast.parse(Path(consumer_module.__file__).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    forbidden = {
        "network_automation.activities",
        "network_automation.cli.render",
        "network_automation.events.producer",
        "network_automation.intent",
        "network_automation.rendering",
    }

    assert not any(
        imported == dependency or imported.startswith(f"{dependency}.")
        for imported in imports
        for dependency in forbidden
    )


@pytest.mark.asyncio
async def test_consumer_runtime_configures_manual_commit_health_and_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    stop_event = asyncio.Event()

    class RuntimeConsumer:
        def __init__(self, config: dict[str, object]) -> None:
            captured["config"] = config

        def subscribe(self, topics: list[str]) -> None:
            captured["topics"] = topics

        def list_topics(self, *, timeout: float) -> object:
            captured["metadata_timeout"] = timeout
            return object()

        def poll(self, timeout: float) -> None:
            captured["poll_timeout"] = timeout
            stop_event.set()
            return None

        def close(self) -> None:
            captured["closed"] = True

    async def connect(address: str, **kwargs: object) -> object:
        captured["address"] = address
        captured["client_options"] = kwargs
        return object()

    monkeypatch.setattr(consumer_module, "Consumer", RuntimeConsumer)
    monkeypatch.setattr(consumer_module.Client, "connect", connect)
    ready = tmp_path / "consumer.ready"
    heartbeat = tmp_path / "consumer.heartbeat"
    settings = SimpleNamespace(
        temporal_address="temporal.test:7233",
        temporal_namespace="default",
        kafka_bootstrap_servers="kafka.test:9092",
        render_consumer_group="consumer.test",
        render_request_topic="requests.test",
        probe_timeout_seconds=7,
    )

    await consumer_module.run_consumer(
        settings,
        stop_event=stop_event,
        ready_path=ready,
        heartbeat_path=heartbeat,
    )

    assert captured["config"] == {
        "bootstrap.servers": "kafka.test:9092",
        "group.id": "consumer.test",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    }
    assert captured["topics"] == ["requests.test"]
    assert captured["metadata_timeout"] == 7
    assert captured["closed"] is True
    assert ready.is_file()
    assert heartbeat.is_file()
