"""FastAPI application for bounded, read-only control-plane observation."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal
from uuid import UUID, uuid4

import uvicorn
from fastapi import FastAPI, Path as ApiPath, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.service import RPCError

from network_automation.api.devices import get_device_detail, get_topology, list_devices
from network_automation.api.health import aggregate_health
from network_automation.api.models import (
    ActivitySection,
    ApiError,
    CountSection,
    DeploymentList,
    DeploymentOverview,
    DeviceDetail,
    DeviceList,
    Overview,
    SourceAvailability,
    SystemHealthSummary,
    TopologyGraph,
    TopologyOverview,
    WorkflowDetail,
    WorkflowList,
    WorkflowOverview,
)
from network_automation.api.workflows import (
    deployment_from_summary,
    get_workflow_detail,
    list_deployments,
    list_workflow_summaries,
    validate_workflow_id,
)
from network_automation.intent.nautobot import NautobotClient, NautobotError
from network_automation.settings import LabSettings

DEVICE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
WORKFLOW_PATTERN = r"^(render-device-config|deploy-device-config):[0-9a-f-]{36}$"
_UNSET = object()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _error(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    body = ApiError(code=code, message=message, request_id=request_id)
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def create_app(
    *,
    settings: LabSettings | None = None,
    nautobot_client: NautobotClient | None = None,
    temporal_client: Any = _UNSET,
) -> FastAPI:
    async def temporal_for(application: FastAPI, *, timeout: float | None = None) -> Any | None:
        if application.state.temporal is not None or not application.state.temporal_dynamic:
            return application.state.temporal
        async with application.state.temporal_lock:
            if application.state.temporal is not None:
                return application.state.temporal
            try:
                application.state.temporal = await asyncio.wait_for(
                    Client.connect(
                        application.state.settings.temporal_address,
                        namespace=application.state.settings.temporal_namespace,
                        data_converter=pydantic_data_converter,
                    ),
                    timeout=(
                        timeout
                        if timeout is not None
                        else application.state.settings.api_probe_timeout_seconds
                    ),
                )
            except Exception:
                return None
        return application.state.temporal

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or LabSettings()
        owns_nautobot = nautobot_client is None
        resolved_nautobot = nautobot_client or NautobotClient(
            str(resolved_settings.nautobot_url),
            resolved_settings.nautobot_token.get_secret_value(),
            timeout=resolved_settings.api_probe_timeout_seconds,
        )
        application.state.settings = resolved_settings
        application.state.nautobot = resolved_nautobot
        application.state.temporal_dynamic = temporal_client is _UNSET
        application.state.temporal = None if temporal_client is _UNSET else temporal_client
        application.state.temporal_lock = asyncio.Lock()
        if application.state.temporal_dynamic:
            await temporal_for(application)
        try:
            yield
        finally:
            if owns_nautobot:
                resolved_nautobot.__exit__()

    application = FastAPI(title="Network Automation Read API", lifespan=lifespan, docs_url=None, redoc_url=None)

    @application.middleware("http")
    async def safety_headers(request: Request, call_next: Any) -> Any:
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request", "Request parameters are invalid", request.state.request_id)

    @application.exception_handler(Exception)
    async def internal_error(request: Request, _: Exception) -> JSONResponse:
        return _error(500, "internal_error", "The request could not be completed", request.state.request_id)

    @application.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.head("/healthz")
    async def healthz_head() -> JSONResponse:
        return JSONResponse(content=None)

    @application.get("/api/health", response_model=SystemHealthSummary)
    async def health(request: Request) -> SystemHealthSummary:
        return await aggregate_health(
            request.app.state.settings, await temporal_for(request.app)
        )

    @application.get("/api/devices", response_model=DeviceList)
    async def devices(request: Request, limit: int = Query(default=50, ge=1, le=100)) -> DeviceList:
        try:
            return await asyncio.wait_for(
                list_devices(
                    request.app.state.nautobot,
                    await temporal_for(request.app),
                    request.app.state.settings,
                    limit=limit,
                ),
                timeout=request.app.state.settings.api_overview_timeout_seconds,
            )
        except TimeoutError:
            observed = _now()
            return DeviceList(
                items=(), count=0, observed_at=observed,
                availability=SourceAvailability(
                    source="nautobot", status="unavailable", observed_at=observed, code="timeout",
                    message="Device inventory timed out",
                ),
            )
        except NautobotError:
            observed = _now()
            return DeviceList(
                items=(), count=0, observed_at=observed,
                availability=SourceAvailability(
                    source="nautobot", status="unavailable", observed_at=observed, code="unreachable",
                    message="Device inventory is unavailable",
                ),
            )

    @application.get("/api/devices/{device_name}", response_model=DeviceDetail)
    async def device_detail(
        request: Request,
        device_name: str = ApiPath(pattern=DEVICE_PATTERN, max_length=128),
        live: bool = Query(default=False),
    ) -> DeviceDetail | JSONResponse:
        try:
            detail = await asyncio.wait_for(
                get_device_detail(
                    request.app.state.nautobot,
                    await temporal_for(request.app),
                    request.app.state.settings,
                    device_name,
                    live=live,
                ),
                timeout=(
                    (
                        request.app.state.settings.api_live_timeout_seconds
                        + 2 * request.app.state.settings.api_overview_timeout_seconds
                        + 1
                    )
                    if live
                    else request.app.state.settings.api_overview_timeout_seconds
                ),
            )
        except TimeoutError:
            return _error(
                504,
                "upstream_timeout",
                "Device detail exceeded its observation budget",
                request.state.request_id,
            )
        if detail is None:
            return _error(404, "not_found", "Device was not found", request.state.request_id)
        return detail

    @application.get("/api/topology", response_model=TopologyGraph)
    async def topology(request: Request) -> TopologyGraph:
        try:
            return await asyncio.wait_for(
                get_topology(
                    request.app.state.nautobot,
                    await temporal_for(request.app),
                    request.app.state.settings,
                ),
                timeout=request.app.state.settings.api_overview_timeout_seconds,
            )
        except TimeoutError:
            observed = _now()
            return TopologyGraph(
                nodes=(), links=(), observed_at=observed,
                availability=SourceAvailability(
                    source="nautobot", status="unavailable", observed_at=observed, code="timeout",
                    message="Topology data timed out",
                ),
            )
        except NautobotError:
            observed = _now()
            return TopologyGraph(
                nodes=(), links=(), observed_at=observed,
                availability=SourceAvailability(
                    source="nautobot", status="unavailable", observed_at=observed, code="unreachable",
                    message="Topology data is unavailable",
                ),
            )

    @application.get("/api/workflows", response_model=WorkflowList)
    async def workflows(
        request: Request,
        limit: int = Query(default=25, ge=1, le=50),
        kind: Literal["render", "deployment"] | None = Query(default=None),
        status: Literal[
            "running", "render_succeeded", "render_failed", "deployment_succeeded",
            "deployment_failed", "execution_failed", "execution_canceled",
            "execution_terminated", "execution_timed_out", "continued_as_new", "unknown",
        ] | None = Query(default=None),
    ) -> WorkflowList:
        temporal = await temporal_for(request.app)
        if temporal is None:
            observed = _now()
            return WorkflowList(items=(), count=0, observed_at=observed, availability=SourceAvailability(
                source="temporal", status="unavailable", observed_at=observed, code="unreachable",
                message="Temporal workflow data is unavailable",
            ))
        try:
            result = await asyncio.wait_for(
                list_workflow_summaries(
                    temporal,
                    limit=limit,
                    hydration_concurrency=request.app.state.settings.api_workflow_hydration_concurrency,
                ),
                timeout=request.app.state.settings.api_overview_timeout_seconds,
            )
        except (RPCError, TimeoutError):
            observed = _now()
            return WorkflowList(items=(), count=0, observed_at=observed, availability=SourceAvailability(
                source="temporal", status="unavailable", observed_at=observed, code="unreachable",
                message="Temporal workflow data is unavailable",
            ))
        items = tuple(item for item in result.items if (kind is None or item.kind == kind) and (status is None or item.outcome == status))
        return result.model_copy(update={"items": items, "count": len(items)})

    @application.get("/api/workflows/{workflow_id}", response_model=WorkflowDetail)
    async def workflow_detail(
        request: Request,
        workflow_id: str = ApiPath(pattern=WORKFLOW_PATTERN, max_length=128),
        run_id: UUID | None = Query(default=None),
    ) -> WorkflowDetail | JSONResponse:
        try:
            validate_workflow_id(workflow_id)
        except ValueError:
            return _error(422, "invalid_request", "Workflow identifier is invalid", request.state.request_id)
        temporal = await temporal_for(request.app)
        if temporal is None:
            return _error(504, "upstream_timeout", "Workflow detail is unavailable", request.state.request_id)
        try:
            detail = await asyncio.wait_for(
                get_workflow_detail(
                    temporal,
                    workflow_id,
                    str(run_id) if run_id else None,
                    request.app.state.settings.api_artifact_root,
                    history_timeout=request.app.state.settings.api_overview_timeout_seconds,
                ),
                timeout=2 * request.app.state.settings.api_overview_timeout_seconds + 1,
            )
        except TimeoutError:
            return _error(504, "upstream_timeout", "Workflow detail timed out", request.state.request_id)
        if detail is None:
            return _error(404, "not_found", "Workflow was not found", request.state.request_id)
        return detail

    @application.get("/api/deployments", response_model=DeploymentList)
    async def deployments(
        request: Request,
        limit: int = Query(default=25, ge=1, le=50),
        status: Literal["queued", "preparing", "deploying", "validating", "succeeded", "failed", "unknown"] | None = Query(default=None),
    ) -> DeploymentList:
        temporal = await temporal_for(request.app)
        if temporal is None:
            observed = _now()
            return DeploymentList(items=(), count=0, observed_at=observed, availability=SourceAvailability(
                source="temporal", status="unavailable", observed_at=observed, code="unreachable",
                message="Temporal deployment data is unavailable",
            ))
        try:
            result = await asyncio.wait_for(
                list_deployments(
                    temporal,
                    limit=limit,
                    artifact_root=request.app.state.settings.api_artifact_root,
                    hydration_concurrency=request.app.state.settings.api_workflow_hydration_concurrency,
                ),
                timeout=request.app.state.settings.api_overview_timeout_seconds,
            )
        except (RPCError, TimeoutError):
            observed = _now()
            return DeploymentList(items=(), count=0, observed_at=observed, availability=SourceAvailability(
                source="temporal", status="unavailable", observed_at=observed, code="unreachable",
                message="Temporal deployment data is unavailable",
            ))
        items = tuple(item for item in result.items if status is None or item.status == status)
        return result.model_copy(update={"items": items, "count": len(items)})

    @application.get("/api/deployments/{workflow_id}", response_model=WorkflowDetail)
    async def deployment_detail(
        request: Request,
        workflow_id: str = ApiPath(pattern=WORKFLOW_PATTERN, max_length=128),
        run_id: UUID | None = Query(default=None),
    ) -> WorkflowDetail | JSONResponse:
        try:
            validate_workflow_id(workflow_id, deployment_only=True)
        except ValueError:
            return _error(422, "invalid_request", "Deployment identifier is invalid", request.state.request_id)
        return await workflow_detail(request, workflow_id, run_id)

    @application.get("/api/overview", response_model=Overview)
    async def overview(request: Request) -> Overview:
        settings = request.app.state.settings
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settings.api_overview_timeout_seconds
        observed = _now()
        unavailable_nautobot = SourceAvailability(
            source="nautobot", status="unavailable", observed_at=observed, code="timeout",
            message="Nautobot data is unavailable",
        )
        unavailable_temporal = SourceAvailability(
            source="temporal", status="unavailable", observed_at=observed, code="timeout",
            message="Temporal workflow data is unavailable",
        )

        async def bounded(value: Any, fallback: Any) -> Any:
            try:
                return await asyncio.wait_for(
                    value, timeout=max(0.001, deadline - loop.time())
                )
            except (NautobotError, RPCError, TimeoutError):
                return fallback

        fallback_health = SystemHealthSummary(
            overall_status="unavailable", observed_at=observed,
            nautobot=unavailable_nautobot,
            kafka=SourceAvailability(source="kafka", status="unavailable", observed_at=observed, code="timeout", message="Kafka is unavailable"),
            temporal=unavailable_temporal,
            worker=SourceAvailability(source="worker", status="unavailable", observed_at=observed, code="timeout", message="Automation worker status is unavailable"),
            consumer=SourceAvailability(source="consumer", status="unavailable", observed_at=observed, code="timeout", message="Event consumer status is unavailable"),
            device_validation=SourceAvailability(source="device", status="unknown", observed_at=observed, code="unknown", message="Live device capability is unknown"),
        )
        fallback_devices = DeviceList(items=(), count=0, observed_at=observed, availability=unavailable_nautobot)
        fallback_topology = TopologyGraph(nodes=(), links=(), observed_at=observed, availability=unavailable_nautobot)
        fallback_workflows = WorkflowList(items=(), count=0, observed_at=observed, availability=unavailable_temporal)
        temporal = await temporal_for(
            request.app,
            timeout=min(
                settings.api_probe_timeout_seconds,
                max(0.001, deadline - loop.time()),
            ),
        )
        inventory_task = asyncio.create_task(
            asyncio.to_thread(
                request.app.state.nautobot.list_inventory_devices,
                limit=settings.api_device_limit,
            )
        )

        async def devices_from_inventory() -> DeviceList:
            return await list_devices(
                request.app.state.nautobot,
                None,
                settings,
                limit=settings.api_device_limit,
                inventory_devices=await inventory_task,
            )

        async def topology_from_inventory() -> TopologyGraph:
            return await get_topology(
                request.app.state.nautobot,
                inventory_devices=await inventory_task,
            )

        health_task = bounded(aggregate_health(settings, temporal), fallback_health)
        devices_task = bounded(devices_from_inventory(), fallback_devices)
        topology_task = bounded(topology_from_inventory(), fallback_topology)
        if temporal is None:
            workflow_value = asyncio.sleep(0, result=fallback_workflows)
        else:
            workflow_value = list_workflow_summaries(
                temporal,
                limit=settings.api_workflow_limit,
                hydration_limit=settings.api_overview_workflow_limit,
                hydration_concurrency=settings.api_workflow_hydration_concurrency,
            )
        workflow_task = bounded(workflow_value, fallback_workflows)
        health_data, device_data, topology_data, workflow_data = await asyncio.gather(
            health_task, devices_task, topology_task, workflow_task,
        )
        recent_workflows = workflow_data.items[:settings.api_overview_workflow_limit]
        recent_deployments = tuple(
            deployment_from_summary(item, None, settings.api_artifact_root)
            for item in recent_workflows if item.kind == "deployment"
        )
        latest_deployments = {}
        for item in recent_deployments:
            if item.device_name is not None and item.device_name not in latest_deployments:
                latest_deployments[item.device_name] = item
        topology_nodes = tuple(
            node.model_copy(update={
                "status": (
                    "healthy"
                    if latest_deployments[node.id].validation_status == "passed"
                    else "failed"
                    if latest_deployments[node.id].validation_status == "failed"
                    or latest_deployments[node.id].status == "failed"
                    else "healthy"
                    if latest_deployments[node.id].status == "succeeded"
                    else node.status
                ),
                "status_source": (
                    "validation"
                    if latest_deployments[node.id].validation_status in {"passed", "failed"}
                    else "deployment"
                    if latest_deployments[node.id].status in {"succeeded", "failed"}
                    else node.status_source
                ),
            })
            if node.id in latest_deployments
            else node
            for node in topology_data.nodes
        )
        return Overview(
            observed_at=_now(), health=health_data,
            devices=CountSection(availability=device_data.availability, total=device_data.count if device_data.availability.status == "healthy" else None),
            workflows=WorkflowOverview(
                availability=workflow_data.availability,
                active_count=sum(item.execution_status == "running" for item in workflow_data.items),
                recent=recent_workflows,
            ),
            deployments=DeploymentOverview(
                availability=workflow_data.availability,
                recent_successes=tuple(item for item in recent_deployments if item.status == "succeeded"),
                recent_failures=tuple(item for item in recent_deployments if item.status == "failed"),
            ),
            topology=TopologyOverview(
                availability=topology_data.availability, nodes=topology_nodes, links=topology_data.links,
            ),
            activity=ActivitySection(availability=workflow_data.availability, items=recent_workflows),
        )

    return application


app = create_app()


def main() -> None:
    uvicorn.run("network_automation.api.app:app", host="0.0.0.0", port=8000)
