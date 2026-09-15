import asyncio
import time
from dataclasses import replace
from ipaddress import IPv4Address
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from network_automation.api.app import create_app
from network_automation.api import devices as api_devices
from network_automation.intent.models import (
    BgpIntent,
    BgpNeighborIntent,
    DeviceIntent,
    InterfaceIntent,
    LoopbackIntent,
)
from network_automation.intent.nautobot import (
    NautobotDeploymentIntent,
    NautobotError,
    NautobotInventoryDevice,
    NautobotTopologyInterface,
)
from network_automation.settings import LabSettings


class Nautobot:
    def list_inventory_devices(self, *, limit: int):
        return (
            NautobotInventoryDevice(
                id="one", name="leaf01", role="leaf", platform="Nokia SR Linux",
                location="lab", management_address=IPv4Address("192.0.2.10"), status="Active",
            ),
            NautobotInventoryDevice(
                id="two", name="leaf02", role="leaf", platform="Nokia SR Linux",
                location=None, management_address=None, status="Planned",
            ),
        )[:limit]

    def list_topology_interfaces(self, devices):
        return (
            NautobotTopologyInterface("leaf01", "ethernet-1/1", (), "leaf02", "ethernet-1/1"),
            NautobotTopologyInterface("leaf02", "ethernet-1/1", (), "leaf01", "ethernet-1/1"),
        )

    def get_deployment_intent(self, name):
        raise NautobotError("intent unavailable")


def settings() -> LabSettings:
    return LabSettings(_env_file=None, nautobot_password="password", nautobot_token="token")


def _snapshot(name: str, address: str, neighbor: str) -> NautobotDeploymentIntent:
    return NautobotDeploymentIntent(
        intent=DeviceIntent(
            name=name,
            platform="nokia_srl",
            role="leaf",
            loopback=LoopbackIntent(ipv4=f"192.0.2.{1 if name == 'leaf01' else 2}/32"),
            interfaces=(
                InterfaceIntent(name="ethernet-1/1", description="peer", ipv4=address),
            ),
            bgp=BgpIntent(
                local_asn=65001 if name == "leaf01" else 65002,
                neighbors=(BgpNeighborIntent(address=neighbor, remote_asn=65002 if name == "leaf01" else 65001),),
            ),
        ),
        management_address=IPv4Address("192.0.2.10" if name == "leaf01" else "192.0.2.11"),
    )


class LogicalNautobot(Nautobot):
    def list_inventory_devices(self, *, limit: int):
        devices = super().list_inventory_devices(limit=limit)
        neighbors = {
            "leaf01": (IPv4Address("10.0.0.1"),),
            "leaf02": (IPv4Address("10.0.0.0"),),
        }
        return tuple(
            replace(device, bgp_neighbors=neighbors[device.name])
            for device in devices
        )

    def list_topology_interfaces(self, devices):
        return (
            NautobotTopologyInterface("leaf01", "ethernet-1/1", (IPv4Address("10.0.0.0"),), None, None),
            NautobotTopologyInterface("leaf02", "ethernet-1/1", (IPv4Address("10.0.0.1"),), None, None),
        )

    def get_deployment_intent(self, name):
        if name == "leaf01":
            return _snapshot("leaf01", "10.0.0.0/31", "10.0.0.1")
        return _snapshot("leaf02", "10.0.0.1/31", "10.0.0.0")


def test_device_list_exposes_only_normalized_inventory_fields() -> None:
    app = create_app(settings=settings(), nautobot_client=Nautobot(), temporal_client=None)
    with TestClient(app) as client:
        response = client.get("/api/devices")

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["items"][0]["management_address"] == "192.0.2.10"
    assert "id" not in response.json()["items"][0]


def test_topology_deduplicates_exact_physical_endpoints() -> None:
    app = create_app(settings=settings(), nautobot_client=Nautobot(), temporal_client=None)
    with TestClient(app) as client:
        response = client.get("/api/topology")

    assert response.status_code == 200
    assert [link["kind"] for link in response.json()["links"]] == ["physical"]
    assert len(response.json()["nodes"]) == 2


def test_unknown_device_returns_safe_not_found() -> None:
    app = create_app(settings=settings(), nautobot_client=Nautobot(), temporal_client=None)
    with TestClient(app) as client:
        response = client.get("/api/devices/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_bgp_topology_requires_reciprocal_intent_and_deduplicates_endpoints() -> None:
    topology = asyncio.run(api_devices.get_topology(LogicalNautobot()))

    assert len(topology.links) == 1
    link = topology.links[0]
    assert link.kind == "bgp"
    assert (link.source_device, link.source_interface) == ("leaf01", "ethernet-1/1")
    assert (link.target_device, link.target_interface) == ("leaf02", "ethernet-1/1")


def test_bgp_topology_excludes_one_sided_and_marks_partial_intent() -> None:
    class Partial(LogicalNautobot):
        def list_inventory_devices(self, *, limit: int):
            return tuple(
                replace(
                    device,
                    bgp_neighbors=()
                    if device.name == "leaf02"
                    else device.bgp_neighbors,
                    bgp_intent_available=device.name != "leaf02",
                )
                for device in super().list_inventory_devices(limit=limit)
            )

    topology = asyncio.run(api_devices.get_topology(Partial()))

    assert not topology.links
    assert topology.availability.status == "degraded"
    assert topology.availability.code == "invalid_response"


def test_topology_node_status_prefers_retained_validation_then_inventory() -> None:
    active = Nautobot().list_inventory_devices(limit=2)[0]

    assert api_devices._node_status(active, None) == ("healthy", "inventory")
    assert api_devices._node_status(
        active, SimpleNamespace(validation_status="failed", status="failed")
    ) == ("failed", "validation")
    assert api_devices._node_status(
        active, SimpleNamespace(validation_status="unavailable", status="succeeded")
    ) == ("healthy", "deployment")


def test_topology_applies_retained_deployment_status(monkeypatch) -> None:
    workflow = SimpleNamespace(
        kind="deployment",
        device_name="leaf01",
        workflow_id="deploy-device-config:00000000-0000-4000-8000-000000000001",
        run_id="run",
    )
    workflows = SimpleNamespace(items=(workflow,))

    async def projections(*args, **kwargs):
        return workflows, {}

    deployment = SimpleNamespace(validation_status="failed", status="failed")
    monkeypatch.setattr(api_devices, "list_workflow_projections", projections)
    monkeypatch.setattr(api_devices, "deployment_from_summary", lambda *args: deployment)

    topology = asyncio.run(
        api_devices.get_topology(LogicalNautobot(), object(), settings())
    )

    leaf01 = next(node for node in topology.nodes if node.id == "leaf01")
    assert leaf01.status == "failed"
    assert leaf01.status_source == "validation"


def test_live_timeout_preserves_inventory_and_invokes_one_read(monkeypatch) -> None:
    calls = 0

    def slow_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        time.sleep(1.1)
        return {}

    monkeypatch.setattr(api_devices, "read_srlinux_native_state", slow_read)
    bounded = settings().model_copy(update={
        "api_live_timeout_seconds": 1,
        "api_overview_timeout_seconds": 1,
        "device_gnmi_timeout_seconds": 1,
        "device_username": "admin",
        "device_password": SecretStr("password"),
    })
    app = create_app(
        settings=bounded, nautobot_client=LogicalNautobot(), temporal_client=None
    )
    with TestClient(app) as client:
        response = client.get("/api/devices/leaf01?live=true")

    assert response.status_code == 200
    assert response.json()["summary"]["name"] == "leaf01"
    assert response.json()["intent"]["data"]["hostname"] == "leaf01"
    assert response.json()["live_state"]["data"] is None
    assert response.json()["live_state"]["availability"]["code"] == "timeout"
    assert calls == 1


def test_direct_topology_route_has_an_aggregate_timeout(monkeypatch) -> None:
    async def slow_topology(*args, **kwargs):
        await asyncio.sleep(2)

    monkeypatch.setitem(create_app.__globals__, "get_topology", slow_topology)
    bounded = settings().model_copy(update={"api_overview_timeout_seconds": 1})
    app = create_app(settings=bounded, nautobot_client=Nautobot(), temporal_client=None)
    with TestClient(app) as client:
        response = client.get("/api/topology")

    assert response.status_code == 200
    assert response.json()["availability"]["code"] == "timeout"
