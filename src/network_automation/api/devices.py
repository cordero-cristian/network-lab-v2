"""Nautobot-owned device and topology projections with optional one-shot live state."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from temporalio.service import RPCError

from network_automation.api.models import (
    ArtifactSummary,
    AvailabilityEnvelope,
    DeviceDetail,
    DeviceList,
    DeviceSummary,
    IntendedBgpNeighbor,
    IntendedInterface,
    IntendedStateSummary,
    LiveStateSummary,
    SourceAvailability,
    TopologyGraph,
    TopologyLink,
    TopologyNode,
    ValidationSummary,
)
from network_automation.api.workflows import deployment_from_summary, list_workflow_projections
from network_automation.devices.read_state import read_srlinux_native_state
from network_automation.devices.validation import expected_state_from_intent, validation_result
from network_automation.events.models import ArtifactIdentity, DeploymentTarget, PreparedDeployment
from network_automation.intent.nautobot import (
    NautobotClient,
    NautobotError,
    NautobotInventoryDevice,
)
from network_automation.settings import LabSettings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def availability(source: str, status: str = "healthy", code: str = "ok", message: str | None = None) -> SourceAvailability:
    return SourceAvailability(source=source, status=status, observed_at=_now(), code=code, message=message)


def _device_summary(
    device: NautobotInventoryDevice,
    deployments: dict[str, Any],
    observed_at: datetime,
    *,
    temporal_available: bool,
) -> DeviceSummary:
    deployment = deployments.get(device.name)
    validation = "unknown" if temporal_available else "unavailable"
    if deployment is not None:
        validation = deployment.validation_status
    return DeviceSummary(
        name=device.name, role=device.role, platform=device.platform, location=device.location,
        management_address=device.management_address, inventory_status=device.status,
        last_deployment=deployment, validation_status=validation, observed_at=observed_at,
    )


async def list_devices(
    nautobot: NautobotClient,
    temporal: Any | None,
    settings: LabSettings,
    *,
    limit: int,
    inventory_devices: tuple[NautobotInventoryDevice, ...] | None = None,
) -> DeviceList:
    observed_at = _now()
    devices = (
        inventory_devices[:limit]
        if inventory_devices is not None
        else await asyncio.to_thread(nautobot.list_inventory_devices, limit=limit)
    )
    latest: dict[str, Any] = {}
    temporal_available = temporal is not None
    if temporal is not None:
        try:
            workflows, results = await list_workflow_projections(
                temporal,
                limit=settings.api_workflow_limit,
                hydration_concurrency=settings.api_workflow_hydration_concurrency,
            )
            for item in workflows.items:
                if item.kind != "deployment" or item.device_name is None or item.device_name in latest:
                    continue
                latest[item.device_name] = deployment_from_summary(
                    item, results.get((item.workflow_id, item.run_id)), settings.api_artifact_root
                )
        except (RPCError, TimeoutError):
            temporal_available = False
    items = tuple(
        _device_summary(
            device,
            latest,
            observed_at,
            temporal_available=temporal_available,
        )
        for device in devices
    )
    return DeviceList(items=items, count=len(items), observed_at=observed_at, availability=availability("nautobot"))


def _intent_summary(intent: Any) -> IntendedStateSummary:
    return IntendedStateSummary(
        hostname=intent.name, loopback=intent.loopback.ipv4,
        routed_interfaces=tuple(
            IntendedInterface(name=value.name, description=value.description, ipv4=value.ipv4)
            for value in sorted(intent.interfaces, key=lambda item: item.name)
        ),
        bgp_local_asn=intent.bgp.local_asn,
        bgp_neighbors=tuple(
            IntendedBgpNeighbor(address=value.address, remote_asn=value.remote_asn, description=value.description)
            for value in sorted(intent.bgp.neighbors, key=lambda item: item.address)
        ),
    )


async def _live(snapshot: Any, settings: LabSettings) -> LiveStateSummary:
    if settings.device_username is None or settings.device_password is None:
        raise RuntimeError("device settings missing")
    expected = expected_state_from_intent(snapshot.intent)
    prepared = PreparedDeployment(
        artifact=ArtifactIdentity(
            device_name=snapshot.intent.name,
            artifact_path=f"artifacts/configs/{snapshot.intent.name}.cfg",
            sha256="0" * 64,
            byte_count=1,
        ),
        target=DeploymentTarget(
            device_name=snapshot.intent.name, management_address=snapshot.management_address,
            platform="nokia_srl", gnmi_port=settings.device_gnmi_port,
            tls_mode=settings.device_gnmi_tls_mode,
        ),
        expected_state=expected,
    )
    observed = await asyncio.to_thread(
        read_srlinux_native_state,
        prepared,
        username=settings.device_username,
        password=settings.device_password.get_secret_value(),
        timeout_seconds=min(
            settings.device_gnmi_timeout_seconds,
            settings.api_live_timeout_seconds,
        ),
    )
    result = validation_result(prepared, observed)
    checks = [check.model_dump(mode="json") for check in result.checks]
    return LiveStateSummary(
        status=result.status,
        hostname=next((check for check in checks if check["name"] == "system.hostname"), None),
        interfaces=tuple(check for check in checks if str(check["name"]).startswith(("interface.", "subinterface.", "address."))),
        bgp=tuple(check for check in checks if str(check["name"]).startswith("routing.bgp.")),
        mismatch_count=sum(check["status"] == "failed" for check in checks),
        validated_at=result.validated_at,
    )


async def get_device_detail(nautobot: NautobotClient, temporal: Any | None, settings: LabSettings, name: str, *, live: bool) -> DeviceDetail | None:
    inventory = await asyncio.wait_for(
        asyncio.to_thread(nautobot.list_inventory_devices, limit=100),
        timeout=settings.api_overview_timeout_seconds,
    )
    device = next((item for item in inventory if item.name == name), None)
    if device is None:
        return None
    observed_at = _now()
    async def latest_deployment() -> tuple[Any | None, bool]:
        if temporal is None:
            return None, False
        try:
            workflows, results = await asyncio.wait_for(
                list_workflow_projections(
                    temporal,
                    limit=settings.api_workflow_limit,
                    hydration_concurrency=settings.api_workflow_hydration_concurrency,
                ),
                timeout=settings.api_overview_timeout_seconds,
            )
            workflow = next((item for item in workflows.items if item.kind == "deployment" and item.device_name == name), None)
            if workflow:
                return deployment_from_summary(
                    workflow, results.get((workflow.workflow_id, workflow.run_id)), settings.api_artifact_root
                ), True
        except (RPCError, TimeoutError):
            return None, False
        return None, True

    async def deployment_intent() -> Any | None:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(nautobot.get_deployment_intent, name),
                timeout=settings.api_overview_timeout_seconds,
            )
        except (NautobotError, TimeoutError):
            return None

    (latest, temporal_available), snapshot = await asyncio.gather(
        latest_deployment(), deployment_intent()
    )
    summary = _device_summary(
        device,
        {name: latest} if latest else {},
        observed_at,
        temporal_available=temporal_available,
    )
    if snapshot is not None:
        intent = AvailabilityEnvelope(availability=availability("nautobot"), data=_intent_summary(snapshot.intent))
    else:
        intent = AvailabilityEnvelope(
            availability=availability("nautobot", "unavailable", "invalid_response", "Device intent is unavailable"), data=None
        )
    artifact = latest.artifact if latest else None
    artifact_envelope = AvailabilityEnvelope[ArtifactSummary](
        availability=(
            availability("artifact")
            if artifact
            else availability("artifact", "unknown", "history_unavailable", "No retained artifact evidence")
        ),
        data=artifact,
    )
    deployment_envelope = AvailabilityEnvelope(
        availability=(
            availability("temporal")
            if latest
            else availability(
                "temporal",
                "unknown" if temporal_available else "unavailable",
                "history_unavailable" if temporal_available else "unreachable",
                "No retained deployment evidence"
                if temporal_available
                else "Temporal deployment data is unavailable",
            )
        ),
        data=latest,
    )
    historical = AvailabilityEnvelope[ValidationSummary](
        availability=(
            availability("temporal")
            if latest
            else availability(
                "temporal",
                "unknown" if temporal_available else "unavailable",
                "history_unavailable" if temporal_available else "unreachable",
                "No retained validation evidence"
                if temporal_available
                else "Temporal validation data is unavailable",
            )
        ),
        data=(ValidationSummary(status=latest.validation_status) if latest else None),
    )
    live_envelope: AvailabilityEnvelope[LiveStateSummary]
    if not live:
        live_envelope = AvailabilityEnvelope(
            availability=availability("device", "unknown", "not_configured", "Live state was not requested"), data=None
        )
    elif snapshot is None:
        live_envelope = AvailabilityEnvelope(
            availability=availability("device", "unavailable", "invalid_response", "Live state is unavailable"), data=None
        )
    else:
        try:
            live_data = await asyncio.wait_for(_live(snapshot, settings), timeout=settings.api_live_timeout_seconds)
            live_envelope = AvailabilityEnvelope(availability=availability("device"), data=live_data)
        except TimeoutError:
            live_envelope = AvailabilityEnvelope(
                availability=availability("device", "unavailable", "timeout", "Live state read timed out"), data=None
            )
        except Exception:
            live_envelope = AvailabilityEnvelope(
                availability=availability("device", "unavailable", "unreachable", "Live state is unavailable"), data=None
            )
    return DeviceDetail(
        summary=summary, intent=intent, latest_artifact=artifact_envelope,
        latest_deployment=deployment_envelope, historical_validation=historical, live_state=live_envelope,
    )


def _node_status(device: NautobotInventoryDevice, deployment: Any | None) -> tuple[str, str | None]:
    if deployment is not None:
        if deployment.validation_status == "passed":
            return "healthy", "validation"
        if deployment.validation_status == "failed":
            return "failed", "validation"
        if deployment.status == "failed":
            return "failed", "deployment"
        if deployment.status == "succeeded":
            return "healthy", "deployment"
    inventory_status = (device.status or "").casefold()
    if inventory_status == "active":
        return "healthy", "inventory"
    if inventory_status in {"failed", "offline"}:
        return "failed", "inventory"
    if inventory_status in {"maintenance", "decommissioning"}:
        return "degraded", "inventory"
    return "unknown", None


async def get_topology(
    nautobot: NautobotClient,
    temporal: Any | None = None,
    settings: LabSettings | None = None,
    *,
    inventory_devices: tuple[NautobotInventoryDevice, ...] | None = None,
) -> TopologyGraph:
    observed_at = _now()
    devices = (
        inventory_devices[:100]
        if inventory_devices is not None
        else await asyncio.to_thread(nautobot.list_inventory_devices, limit=100)
    )

    interfaces = await asyncio.to_thread(
        nautobot.list_topology_interfaces, devices
    )
    latest: dict[str, Any] = {}
    if temporal is not None and settings is not None:
        try:
            workflows, results = await list_workflow_projections(
                temporal,
                limit=settings.api_workflow_limit,
                hydration_concurrency=settings.api_workflow_hydration_concurrency,
            )
            for item in workflows.items:
                if item.kind != "deployment" or item.device_name is None or item.device_name in latest:
                    continue
                latest[item.device_name] = deployment_from_summary(
                    item,
                    results.get((item.workflow_id, item.run_id)),
                    settings.api_artifact_root,
                )
        except (RPCError, TimeoutError):
            pass
    nodes = []
    for device in sorted(devices, key=lambda item: ((item.role or ""), item.name)):
        status, source = _node_status(device, latest.get(device.name))
        nodes.append(
            TopologyNode(
                id=device.name,
                label=device.name,
                role=device.role,
                platform=device.platform,
                status=status,
                status_source=source,
            )
        )
    device_names = {device.name for device in devices}
    links: dict[str, TopologyLink] = {}
    physical_endpoints = {
        (
            interface.device_name,
            interface.name,
            interface.connected_device,
            interface.connected_interface,
        )
        for interface in interfaces
        if interface.connected_device is not None
        and interface.connected_interface is not None
    }
    for interface in interfaces:
        if (
            interface.connected_device is None
            or interface.connected_interface is None
            or interface.connected_device not in device_names
            or interface.connected_device == interface.device_name
            or (
                interface.connected_device,
                interface.connected_interface,
                interface.device_name,
                interface.name,
            )
            not in physical_endpoints
        ):
            continue
        endpoints = sorted(((interface.device_name, interface.name), (interface.connected_device, interface.connected_interface)))
        key = f"physical:{endpoints[0][0]}:{endpoints[0][1]}:{endpoints[1][0]}:{endpoints[1][1]}"
        link_id = hashlib.sha256(key.encode("ascii")).hexdigest()[:24]
        links[key] = TopologyLink(
            id=link_id, kind="physical", source_device=endpoints[0][0], source_interface=endpoints[0][1],
            target_device=endpoints[1][0], target_interface=endpoints[1][1],
        )
    owners: dict[object, list[tuple[str, str]]] = {}
    for interface in interfaces:
        for address in interface.addresses:
            owners.setdefault(address, []).append((interface.device_name, interface.name))
    directed: dict[tuple[str, str], list[tuple[str, str]]] = {}
    partial_intent = any(not device.bgp_intent_available for device in devices)
    for device in devices:
        for neighbor in device.bgp_neighbors:
            matches = owners.get(neighbor, [])
            if len(matches) != 1 or matches[0][0] == device.name:
                continue
            remote_device, remote_interface = matches[0]
            directed.setdefault((device.name, remote_device), []).append(
                (str(neighbor), remote_interface)
            )

    for source_device, target_device in sorted(directed):
        if source_device >= target_device:
            continue
        forward = directed[(source_device, target_device)]
        reverse = directed.get((target_device, source_device), [])
        if len(forward) != 1 or len(reverse) != 1:
            continue
        source_interface = reverse[0][1]
        target_interface = forward[0][1]
        endpoints = ((source_device, source_interface), (target_device, target_interface))
        key = f"bgp:{endpoints[0][0]}:{endpoints[0][1]}:{endpoints[1][0]}:{endpoints[1][1]}"
        links[key] = TopologyLink(
            id=hashlib.sha256(key.encode("ascii")).hexdigest()[:24], kind="bgp",
            source_device=endpoints[0][0], source_interface=endpoints[0][1],
            target_device=endpoints[1][0], target_interface=endpoints[1][1],
        )
    return TopologyGraph(
        nodes=tuple(nodes), links=tuple(links[key] for key in sorted(links))[:200], observed_at=observed_at,
        availability=(
            availability(
                "nautobot", "degraded", "invalid_response",
                "Some topology intent is unavailable",
            )
            if partial_intent
            else availability("nautobot")
        ),
    )


__all__ = ["get_device_detail", "get_topology", "list_devices"]
