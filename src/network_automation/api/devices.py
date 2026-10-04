"""Nautobot-owned device and topology projections with optional one-shot live state."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from temporalio.service import RPCError

from network_automation.api.models import (
    ArtifactSummary,
    AvailabilityEnvelope,
    ComparisonSources,
    ConfigurationDriftObservation,
    DeviceDetail,
    DeviceList,
    DeviceSummary,
    IntendedBgpNeighbor,
    IntendedInterface,
    IntendedStateSummary,
    OperationalHealthObservation,
    SourceAvailability,
    TopologyGraph,
    TopologyLink,
    TopologyNode,
    ValidationSummary,
)
from network_automation.api.workflows import deployment_from_summary, list_workflow_projections
from network_automation.devices import (
    DeviceAuthenticationError,
    DeviceConnectionError,
    DeviceIdentityError,
    DevicePathError,
    DevicePlatformError,
    DeviceResponseError,
)
from network_automation.devices.comparison import DeviceComparison, compare_device_state
from network_automation.devices.read_state import read_srlinux_native_state
from network_automation.devices.validation import expected_state_from_intent
from network_automation.events.models import ArtifactIdentity, DeploymentTarget, PreparedDeployment
from network_automation.intent.nautobot import (
    NautobotClient,
    NautobotError,
    NautobotInventoryDevice,
)
from network_automation.settings import LabSettings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def availability(
    source: str,
    status: str = "healthy",
    code: str = "ok",
    message: str | None = None,
    *,
    observed_at: datetime | None = None,
) -> SourceAvailability:
    return SourceAvailability(
        source=source,
        status=status,
        observed_at=observed_at or _now(),
        code=code,
        message=message,
    )


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


async def _live(
    snapshot: Any, settings: LabSettings, expected: Any
) -> DeviceComparison:
    if settings.device_username is None or settings.device_password is None:
        raise RuntimeError("device settings missing")
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
    return compare_device_state(expected, observed, _now())


def _comparison_sources(
    observed_at: datetime,
    *,
    intent_status: str = "healthy",
    intent_code: str = "ok",
    intent_message: str | None = None,
    device_status: str = "healthy",
    device_code: str = "ok",
    device_message: str | None = None,
) -> ComparisonSources:
    return ComparisonSources(
        intent=availability(
            "nautobot", intent_status, intent_code, intent_message, observed_at=observed_at
        ),
        device=availability(
            "device", device_status, device_code, device_message, observed_at=observed_at
        ),
    )


def _unavailable_comparison(
    observed_at: datetime, sources: ComparisonSources
) -> tuple[ConfigurationDriftObservation, OperationalHealthObservation]:
    return (
        ConfigurationDriftObservation(
            status="unavailable", sources=sources, result=None, observed_at=observed_at
        ),
        OperationalHealthObservation(
            status="unavailable", sources=sources, result=None, observed_at=observed_at
        ),
    )


def _successful_comparison(
    comparison: DeviceComparison,
) -> tuple[ConfigurationDriftObservation, OperationalHealthObservation]:
    sources = _comparison_sources(comparison.observed_at)
    return (
        ConfigurationDriftObservation(
            status=comparison.configuration.status,
            sources=sources,
            result=comparison.configuration,
            observed_at=comparison.observed_at,
        ),
        OperationalHealthObservation(
            status=comparison.operational.status,
            sources=sources,
            result=comparison.operational,
            observed_at=comparison.observed_at,
        ),
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
        except (NautobotError, TimeoutError, ValidationError):
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
    intent_summary: IntendedStateSummary | None = None
    if snapshot is not None:
        try:
            intent_summary = _intent_summary(snapshot.intent)
        except ValidationError:
            snapshot = None
    if intent_summary is not None:
        intent = AvailabilityEnvelope(
            availability=availability("nautobot"), data=intent_summary
        )
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
    comparison_observed_at = _now()
    if not live:
        configuration_drift, operational_health = _unavailable_comparison(
            comparison_observed_at,
            _comparison_sources(
                comparison_observed_at,
                intent_status="healthy" if snapshot is not None else "unavailable",
                intent_code="ok" if snapshot is not None else "invalid_response",
                intent_message=None if snapshot is not None else "Device intent is unavailable",
                device_status="unknown",
                device_code="not_configured",
                device_message="Live comparison was not requested",
            ),
        )
    elif snapshot is None:
        configuration_drift, operational_health = _unavailable_comparison(
            comparison_observed_at,
            _comparison_sources(
                comparison_observed_at,
                intent_status="unavailable",
                intent_code="invalid_response",
                intent_message="Device intent is unavailable",
                device_status="unknown",
                device_code="not_configured",
                device_message="Live comparison was not attempted",
            ),
        )
    elif settings.device_username is None or settings.device_password is None:
        configuration_drift, operational_health = _unavailable_comparison(
            comparison_observed_at,
            _comparison_sources(
                comparison_observed_at,
                device_status="unavailable",
                device_code="not_configured",
                device_message="Device access is not configured",
            ),
        )
    else:
        try:
            expected = expected_state_from_intent(snapshot.intent)
        except ValidationError:
            configuration_drift, operational_health = _unavailable_comparison(
                comparison_observed_at,
                _comparison_sources(
                    comparison_observed_at,
                    intent_status="unavailable",
                    intent_code="invalid_response",
                    intent_message="Device intent is unavailable",
                    device_status="unknown",
                    device_code="not_configured",
                    device_message="Live comparison was not attempted",
                ),
            )
            return DeviceDetail(
                summary=summary,
                intent=AvailabilityEnvelope(
                    availability=availability(
                        "nautobot",
                        "unavailable",
                        "invalid_response",
                        "Device intent is unavailable",
                    ),
                    data=None,
                ),
                latest_artifact=artifact_envelope,
                latest_deployment=deployment_envelope,
                historical_validation=historical,
                configuration_drift=configuration_drift,
                operational_health=operational_health,
            )
        try:
            comparison = await asyncio.wait_for(
                _live(snapshot, settings, expected), timeout=settings.api_live_timeout_seconds
            )
            configuration_drift, operational_health = _successful_comparison(comparison)
        except TimeoutError:
            comparison_observed_at = _now()
            configuration_drift, operational_health = _unavailable_comparison(
                comparison_observed_at,
                _comparison_sources(
                    comparison_observed_at,
                    device_status="unavailable",
                    device_code="timeout",
                    device_message="Live device read timed out",
                ),
            )
        except DeviceAuthenticationError:
            comparison_observed_at = _now()
            configuration_drift, operational_health = _unavailable_comparison(
                comparison_observed_at,
                _comparison_sources(
                    comparison_observed_at,
                    device_status="unavailable",
                    device_code="unreachable",
                    device_message="Device authentication failed",
                ),
            )
        except DeviceConnectionError:
            comparison_observed_at = _now()
            configuration_drift, operational_health = _unavailable_comparison(
                comparison_observed_at,
                _comparison_sources(
                    comparison_observed_at,
                    device_status="unavailable",
                    device_code="unreachable",
                    device_message="Live device is unavailable",
                ),
            )
        except (
            DeviceIdentityError,
            DevicePathError,
            DevicePlatformError,
            DeviceResponseError,
            ValidationError,
            ValueError,
        ):
            comparison_observed_at = _now()
            configuration_drift, operational_health = _unavailable_comparison(
                comparison_observed_at,
                _comparison_sources(
                    comparison_observed_at,
                    device_status="unavailable",
                    device_code="invalid_response",
                    device_message="Live device response is unavailable",
                ),
            )
    return DeviceDetail(
        summary=summary, intent=intent, latest_artifact=artifact_envelope,
        latest_deployment=deployment_envelope, historical_validation=historical,
        configuration_drift=configuration_drift, operational_health=operational_health,
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
