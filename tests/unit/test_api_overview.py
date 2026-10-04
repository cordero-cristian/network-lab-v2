import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from network_automation.api.app import create_app
from network_automation.api.models import (
    DeviceList,
    SourceAvailability,
    SystemHealthSummary,
    TopologyGraph,
    WorkflowList,
    WorkflowSummary,
)
from network_automation.settings import LabSettings


class EmptyNautobot:
    def list_inventory_devices(self, *, limit: int):
        return ()

    def list_topology_interfaces(self, devices):
        return ()


def settings() -> LabSettings:
    return LabSettings(
        _env_file=None,
        nautobot_password="password",
        nautobot_token="token",
        api_overview_timeout_seconds=1,
    )


def available(source: str) -> SourceAvailability:
    return SourceAvailability(
        source=source, status="healthy", observed_at=datetime.now(timezone.utc), code="ok"
    )


def health() -> SystemHealthSummary:
    observed = datetime.now(timezone.utc)
    return SystemHealthSummary(
        overall_status="healthy",
        observed_at=observed,
        nautobot=available("nautobot"),
        kafka=available("kafka"),
        temporal=available("temporal"),
        worker=available("worker"),
        consumer=available("consumer"),
        device_validation=SourceAvailability(
            source="device", status="unknown", observed_at=observed, code="not_configured"
        ),
    )


def workflow(index: int) -> WorkflowSummary:
    now = datetime.now(timezone.utc)
    return WorkflowSummary(
        workflow_id=f"render-device-config:{uuid4()}",
        run_id=uuid4(),
        kind="render",
        execution_status="running",
        outcome="running",
        started_at=now,
        data_status="partial",
    )


def test_overview_counts_the_bounded_window_but_hydrates_only_eight(monkeypatch) -> None:
    observed = datetime.now(timezone.utc)
    captured = {}

    async def aggregate(*args):
        return health()

    async def devices(*args, **kwargs):
        return DeviceList(
            items=(), count=0, observed_at=observed, availability=available("nautobot")
        )

    async def topology(*args, **kwargs):
        return TopologyGraph(
            nodes=(), links=(), observed_at=observed, availability=available("nautobot")
        )

    async def workflows(*args, **kwargs):
        captured.update(kwargs)
        items = tuple(workflow(index) for index in range(12))
        return WorkflowList(
            items=items, count=len(items), observed_at=observed, availability=available("temporal")
        )

    monkeypatch.setitem(create_app.__globals__, "aggregate_health", aggregate)
    monkeypatch.setitem(create_app.__globals__, "list_devices", devices)
    monkeypatch.setitem(create_app.__globals__, "get_topology", topology)
    monkeypatch.setitem(create_app.__globals__, "list_workflow_summaries", workflows)
    app = create_app(
        settings=settings(), nautobot_client=EmptyNautobot(), temporal_client=object()
    )

    with TestClient(app) as client:
        response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json()["workflows"]["active_count"] == 12
    assert len(response.json()["workflows"]["recent"]) == 8
    assert captured == {
        "limit": 25,
        "hydration_limit": 8,
        "hydration_concurrency": 4,
    }


def test_overview_deadline_preserves_completed_sections(monkeypatch) -> None:
    observed = datetime.now(timezone.utc)

    async def aggregate(*args):
        return health()

    async def slow_devices(*args, **kwargs):
        await asyncio.sleep(2)

    async def topology(*args, **kwargs):
        return TopologyGraph(
            nodes=(), links=(), observed_at=observed, availability=available("nautobot")
        )

    async def workflows(*args, **kwargs):
        return WorkflowList(
            items=(), count=0, observed_at=observed, availability=available("temporal")
        )

    monkeypatch.setitem(create_app.__globals__, "aggregate_health", aggregate)
    monkeypatch.setitem(create_app.__globals__, "list_devices", slow_devices)
    monkeypatch.setitem(create_app.__globals__, "get_topology", topology)
    monkeypatch.setitem(create_app.__globals__, "list_workflow_summaries", workflows)
    app = create_app(
        settings=settings(), nautobot_client=EmptyNautobot(), temporal_client=object()
    )

    started = time.monotonic()
    with TestClient(app) as client:
        response = client.get("/api/overview")

    assert time.monotonic() - started < 1.5
    assert response.status_code == 200
    assert response.json()["devices"]["availability"]["status"] == "unavailable"
    assert response.json()["workflows"]["availability"]["status"] == "healthy"
