"""Independent native dependency health aggregation."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable

from confluent_kafka.admin import AdminClient
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, DescribeTaskQueueRequest

from network_automation import health as native_health
from network_automation.api.models import SourceAvailability, SystemHealthSummary
from network_automation.settings import LabSettings


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _probe(source: str, operation: Callable[[], Any], timeout: int) -> SourceAvailability:
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(asyncio.to_thread(operation), timeout=timeout)
        ok = getattr(result, "ok", True)
        status, code = ("healthy", "ok") if ok else ("unavailable", "unreachable")
        message = None if ok else f"{source.title()} is unavailable"
    except TimeoutError:
        status, code, message = "unavailable", "timeout", f"{source.title()} probe timed out"
    except Exception:
        status, code, message = "unavailable", "unreachable", f"{source.title()} is unavailable"
    return SourceAvailability(
        source=source, status=status, observed_at=_now(),
        duration_ms=min(120_000, int((time.monotonic() - started) * 1000)), code=code, message=message,
    )


async def _temporal_probe(client: Any, timeout: float) -> SourceAvailability:
    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout):
            serving = await client.service_client.check_health()
            if not serving:
                raise RuntimeError
            namespace = getattr(client, "namespace", None)
            if not isinstance(namespace, str) or not namespace:
                raise RuntimeError
            await client.workflow_service.describe_namespace(
                DescribeNamespaceRequest(namespace=namespace)
            )
        return SourceAvailability(
            source="temporal", status="healthy", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="ok",
        )
    except TimeoutError:
        code = "timeout"
    except Exception:
        code = "unreachable"
    return SourceAvailability(
        source="temporal", status="unavailable", observed_at=_now(),
        duration_ms=int((time.monotonic() - started) * 1000), code=code,
        message="Temporal is unavailable",
    )


async def _worker_probe(client: Any, settings: LabSettings) -> SourceAvailability:
    async def describe(queue_type: int) -> Any:
        return await client.workflow_service.describe_task_queue(
            DescribeTaskQueueRequest(
                namespace=settings.temporal_namespace,
                task_queue=TaskQueue(name=settings.temporal_task_queue),
                task_queue_type=queue_type,
            )
        )

    started = time.monotonic()
    try:
        workflow, activity = await asyncio.wait_for(
            asyncio.gather(
                describe(TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW),
                describe(TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY),
            ),
            timeout=settings.api_probe_timeout_seconds,
        )
        healthy = bool(workflow.pollers) and bool(activity.pollers)
        return SourceAvailability(
            source="worker", status="healthy" if healthy else "unavailable", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="ok" if healthy else "no_pollers",
            message=None if healthy else "Automation worker pollers are unavailable",
        )
    except TimeoutError:
        return SourceAvailability(
            source="worker", status="unavailable", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="timeout",
            message="Automation worker status timed out",
        )
    except Exception:
        return SourceAvailability(
            source="worker", status="unavailable", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="unreachable",
            message="Automation worker status is unavailable",
        )


def _consumer_group(settings: LabSettings) -> tuple[bool, bool]:
    admin = AdminClient(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "socket.timeout.ms": settings.api_probe_timeout_seconds * 1000,
        }
    )
    futures = admin.describe_consumer_groups([settings.render_consumer_group])
    description = futures[settings.render_consumer_group].result(settings.api_probe_timeout_seconds)
    state = getattr(description.state, "name", str(description.state)).lower()
    return bool(description.members), "stable" in state


async def _consumer_probe(settings: LabSettings) -> SourceAvailability:
    started = time.monotonic()
    try:
        members, stable = await asyncio.wait_for(
            asyncio.to_thread(_consumer_group, settings), timeout=settings.api_probe_timeout_seconds
        )
        if members and not stable:
            return SourceAvailability(
                source="consumer", status="degraded", observed_at=_now(),
                duration_ms=int((time.monotonic() - started) * 1000), code="unknown",
                message="Event consumer group is not stable",
            )
        return SourceAvailability(
            source="consumer", status="healthy" if members else "unavailable", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="ok" if members else "no_members",
            message=None if members else "Event consumer has no active members",
        )
    except TimeoutError:
        return SourceAvailability(
            source="consumer", status="unavailable", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="timeout",
            message="Event consumer status timed out",
        )
    except Exception:
        return SourceAvailability(
            source="consumer", status="unavailable", observed_at=_now(),
            duration_ms=int((time.monotonic() - started) * 1000), code="unreachable",
            message="Event consumer status is unavailable",
        )


async def aggregate_health(settings: LabSettings, temporal: Any | None) -> SystemHealthSummary:
    probe_settings = settings.model_copy(
        update={"probe_timeout_seconds": settings.api_probe_timeout_seconds}
    )
    nautobot_task = _probe("nautobot", lambda: native_health.check_nautobot(probe_settings), settings.api_probe_timeout_seconds)
    kafka_task = _probe("kafka", lambda: native_health.check_kafka(probe_settings), settings.api_probe_timeout_seconds)
    if temporal is None:
        temporal_task = asyncio.sleep(0, result=SourceAvailability(
            source="temporal", status="unavailable", observed_at=_now(), code="unreachable",
            message="Temporal is unavailable",
        ))
        worker_task = asyncio.sleep(0, result=SourceAvailability(
            source="worker", status="unavailable", observed_at=_now(), code="unreachable",
            message="Automation worker status is unavailable",
        ))
    else:
        temporal_task = _temporal_probe(temporal, settings.api_probe_timeout_seconds)
        worker_task = _worker_probe(temporal, settings)
    consumer_task = _consumer_probe(settings)
    nautobot, kafka, temporal_status, worker, consumer = await asyncio.gather(
        nautobot_task, kafka_task, temporal_task, worker_task, consumer_task
    )
    configured = settings.device_username is not None and settings.device_password is not None
    device = SourceAvailability(
        source="device", status="healthy" if configured else "unknown", observed_at=_now(),
        code="ok" if configured else "not_configured",
        message=None if configured else "Live device access is not configured",
    )
    required = (nautobot, kafka, temporal_status, worker, consumer)
    authoritative = (nautobot, temporal_status)
    overall = "healthy" if all(item.status == "healthy" for item in required) else "degraded"
    if all(item.status == "unavailable" for item in authoritative):
        overall = "unavailable"
    return SystemHealthSummary(
        overall_status=overall, observed_at=_now(), nautobot=nautobot, kafka=kafka,
        temporal=temporal_status, worker=worker, consumer=consumer, device_validation=device,
    )


__all__ = ["aggregate_health"]
