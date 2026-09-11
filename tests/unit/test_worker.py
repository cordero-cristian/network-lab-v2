from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter

from network_automation import worker
from network_automation.activities.rendering import (
    publish_render_result,
    render_device_artifact,
)
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow


@pytest.mark.asyncio
async def test_worker_registers_one_workflow_five_activities_and_bounded_executor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from network_automation.activities.deployment import (
        deploy_device_artifact,
        prepare_device_deployment,
        validate_device_state,
    )

    connected: dict[str, object] = {}
    registered: dict[str, object] = {}
    lifecycle: list[str] = []
    client = object()

    async def connect(address: str, **kwargs: object) -> object:
        connected["address"] = address
        connected.update(kwargs)
        return client

    class FakeWorker:
        def __init__(self, received_client: object, **kwargs: object) -> None:
            assert received_client is client
            registered.update(kwargs)

        async def __aenter__(self) -> FakeWorker:
            lifecycle.append("started")
            return self

        async def __aexit__(self, *args: object) -> None:
            lifecycle.append("stopped")

    monkeypatch.setattr(worker.Client, "connect", connect)
    monkeypatch.setattr(worker, "Worker", FakeWorker)
    stop_event = asyncio.Event()
    stop_event.set()
    ready_path = tmp_path / "network-worker.ready"
    heartbeat_path = tmp_path / "network-worker.heartbeat"
    settings = SimpleNamespace(
        temporal_address="temporal.test:7233",
        temporal_namespace="automation",
        temporal_task_queue="network-automation",
    )

    await worker.run_worker(
        settings,
        stop_event=stop_event,
        ready_path=ready_path,
        heartbeat_path=heartbeat_path,
    )

    assert connected == {
        "address": "temporal.test:7233",
        "namespace": "automation",
        "data_converter": pydantic_data_converter,
    }
    assert registered["task_queue"] == "network-automation"
    assert registered["workflows"] == [RenderDeviceConfigWorkflow]
    assert registered["activities"] == [
        render_device_artifact,
        publish_render_result,
        prepare_device_deployment,
        deploy_device_artifact,
        validate_device_state,
    ]
    executor = registered["activity_executor"]
    assert isinstance(executor, ThreadPoolExecutor)
    assert 1 <= executor._max_workers <= 32
    assert lifecycle == ["started", "stopped"]
    assert ready_path.is_file()
    assert heartbeat_path.is_file()


@pytest.mark.asyncio
async def test_worker_health_file_is_refreshed_until_graceful_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready_touches: list[float] = []
    heartbeat_touches: list[float] = []
    stop_event = asyncio.Event()

    class ReadyPath:
        def touch(self, *args: object, **kwargs: object) -> None:
            ready_touches.append(asyncio.get_running_loop().time())

    class HeartbeatPath:
        def touch(self, *args: object, **kwargs: object) -> None:
            heartbeat_touches.append(asyncio.get_running_loop().time())
            if len(heartbeat_touches) == 2:
                stop_event.set()

    class FakeWorker:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        async def __aenter__(self) -> FakeWorker:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    async def connect(*_: object, **__: object) -> object:
        return object()

    monkeypatch.setattr(worker.Client, "connect", connect)
    monkeypatch.setattr(worker, "Worker", FakeWorker)
    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.001)
    settings = SimpleNamespace(
        temporal_address="temporal.test:7233",
        temporal_namespace="automation",
        temporal_task_queue="network-automation",
    )

    await asyncio.wait_for(
        worker.run_worker(
            settings,
            stop_event=stop_event,
            ready_path=ReadyPath(),
            heartbeat_path=HeartbeatPath(),
        ),
        timeout=1,
    )

    assert len(ready_touches) == 1
    assert len(heartbeat_touches) == 2
    assert heartbeat_touches[1] > heartbeat_touches[0]


def test_worker_startup_failure_is_nonzero_and_redacts_exception_detail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fail(*_: object, **__: object) -> None:
        raise ConnectionError("temporal rejected token=super-secret")

    monkeypatch.setattr(worker, "run_worker", fail)

    assert worker.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ConnectionError" in captured.err
    assert "super-secret" not in captured.err
