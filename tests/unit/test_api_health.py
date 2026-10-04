import asyncio
import time
from types import SimpleNamespace

from network_automation.api import health
from network_automation.health import CheckResult
from network_automation.settings import LabSettings


class Temporal:
    namespace = "default"

    class ServiceClient:
        async def check_health(self):
            return True

    class WorkflowService:
        async def describe_namespace(self, request):
            return SimpleNamespace()

        async def describe_task_queue(self, request):
            return SimpleNamespace(pollers=[SimpleNamespace(identity="worker")])

    service_client = ServiceClient()
    workflow_service = WorkflowService()


def settings() -> LabSettings:
    return LabSettings(
        _env_file=None, nautobot_password="password", nautobot_token="token",
        device_username="admin", device_password="device-password",
    )


def test_health_requires_native_sources_pollers_and_consumer_members(monkeypatch) -> None:
    monkeypatch.setattr(health.native_health, "check_nautobot", lambda value: CheckResult("nautobot", True, "ok"))
    monkeypatch.setattr(health.native_health, "check_kafka", lambda value: CheckResult("kafka", True, "ok"))
    monkeypatch.setattr(health, "_consumer_group", lambda value: (True, True))

    result = asyncio.run(health.aggregate_health(settings(), Temporal()))

    assert result.overall_status == "healthy"
    assert result.worker.status == "healthy"
    assert result.consumer.status == "healthy"
    assert result.device_validation.status == "healthy"


def test_health_degrades_without_hiding_available_source(monkeypatch) -> None:
    monkeypatch.setattr(health.native_health, "check_nautobot", lambda value: CheckResult("nautobot", True, "ok"))
    monkeypatch.setattr(health.native_health, "check_kafka", lambda value: CheckResult("kafka", False, "secret raw error"))
    monkeypatch.setattr(health, "_consumer_group", lambda value: (False, True))

    result = asyncio.run(health.aggregate_health(settings(), Temporal()))

    assert result.overall_status == "degraded"
    assert result.nautobot.status == "healthy"
    assert result.kafka.status == "unavailable"
    assert "secret raw error" not in result.model_dump_json()


def test_temporal_health_requires_the_configured_namespace() -> None:
    class MissingNamespaceTemporal(Temporal):
        class WorkflowService(Temporal.WorkflowService):
            async def describe_namespace(self, request):
                raise RuntimeError("missing")

        workflow_service = WorkflowService()

    result = asyncio.run(health._temporal_probe(MissingNamespaceTemporal(), 1))

    assert result.status == "unavailable"
    assert result.code == "unreachable"


def test_consumer_group_with_members_must_be_stable(monkeypatch) -> None:
    monkeypatch.setattr(health, "_consumer_group", lambda value: (True, False))

    result = asyncio.run(health._consumer_probe(settings()))

    assert result.status == "degraded"
    assert result.code == "unknown"


def test_worker_and_consumer_timeouts_have_timeout_codes(monkeypatch) -> None:
    class SlowTemporal(Temporal):
        class WorkflowService(Temporal.WorkflowService):
            async def describe_task_queue(self, request):
                await asyncio.sleep(2)

        workflow_service = WorkflowService()

    async def timed_out_to_thread(*args, **kwargs):
        raise TimeoutError

    bounded = settings().model_copy(update={"api_probe_timeout_seconds": 1})
    worker = asyncio.run(health._worker_probe(SlowTemporal(), bounded))
    monkeypatch.setattr(health.asyncio, "to_thread", timed_out_to_thread)
    consumer = asyncio.run(health._consumer_probe(bounded))

    assert worker.code == "timeout"
    assert consumer.code == "timeout"


def test_temporal_probe_uses_one_aggregate_deadline() -> None:
    class SlowTemporal(Temporal):
        class ServiceClient:
            async def check_health(self):
                await asyncio.sleep(0.6)
                return True

        class WorkflowService(Temporal.WorkflowService):
            async def describe_namespace(self, request):
                await asyncio.sleep(0.6)

        service_client = ServiceClient()
        workflow_service = WorkflowService()

    started = time.monotonic()
    result = asyncio.run(health._temporal_probe(SlowTemporal(), 1))

    assert time.monotonic() - started < 1.2
    assert result.code == "timeout"
