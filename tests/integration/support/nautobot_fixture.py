"""Test-owned Nautobot object creation and exact cleanup."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from network_automation.settings import LabSettings


class FixtureApi:
    def __init__(self, settings: LabSettings) -> None:
        self.base_url = str(settings.nautobot_url).rstrip("/") + "/api/"
        self.client = httpx.Client(
            headers={
                "Authorization": f"Token {settings.nautobot_token.get_secret_value()}",
                "Accept": "application/json",
            },
            timeout=settings.probe_timeout_seconds,
        )
        self.created: list[tuple[str, str]] = []

    def close(self) -> None:
        self.client.close()

    def content_type(self, app_label: str, model: str) -> str:
        response = self.client.get(
            f"{self.base_url}extras/content-types/",
            params={"app_label": app_label, "model": model},
        )
        response.raise_for_status()
        results = response.json()["results"]
        assert len(results) == 1
        assert results[0]["app_label"] == app_label
        assert results[0]["model"] == model
        return f"{app_label}.{model}"

    def create(self, endpoint: str, payload: Mapping[str, object]) -> dict[str, object]:
        response = self.client.post(f"{self.base_url}{endpoint}/", json=payload)
        response.raise_for_status()
        created = response.json()
        object_id = created["id"]
        assert isinstance(object_id, str)
        self.created.append((endpoint, object_id))
        return created

    def update(
        self, endpoint: str, object_id: object, payload: Mapping[str, object]
    ) -> dict[str, object]:
        assert isinstance(object_id, str)
        response = self.client.patch(
            f"{self.base_url}{endpoint}/{object_id}/", json=payload
        )
        response.raise_for_status()
        updated = response.json()
        assert updated["id"] == object_id
        return updated

    def cleanup(self) -> None:
        failures: list[str] = []
        for endpoint, object_id in reversed(self.created):
            object_url = f"{self.base_url}{endpoint}/{object_id}/"
            try:
                response = self.client.delete(object_url)
            except httpx.HTTPError as exc:
                failures.append(f"{endpoint}/{object_id}: DELETE {type(exc).__name__}")
                continue
            if response.status_code not in {204, 404}:
                failures.append(f"{endpoint}/{object_id}: HTTP {response.status_code}")
                continue
            try:
                verification = self.client.get(object_url)
            except httpx.HTTPError as exc:
                failures.append(f"{endpoint}/{object_id}: GET {type(exc).__name__}")
                continue
            if verification.status_code != 404:
                failures.append(
                    f"{endpoint}/{object_id}: still present (HTTP {verification.status_code})"
                )
        assert not failures, f"fixture cleanup failures: {failures}"


def create_render_device(
    fixture: FixtureApi,
    *,
    marker: str,
    device_name: str,
    network_driver: str = "nokia_srl",
) -> None:
    content_types = {
        name: fixture.content_type(app, model)
        for name, app, model in (
            ("device", "dcim", "device"),
            ("interface", "dcim", "interface"),
            ("location", "dcim", "location"),
            ("prefix", "ipam", "prefix"),
            ("ipaddress", "ipam", "ipaddress"),
        )
    }
    status = fixture.create(
        "extras/statuses",
        {
            "name": marker,
            "color": "9e9e9e",
            "content_types": list(content_types.values()),
        },
    )
    namespace = fixture.create("ipam/namespaces", {"name": marker})
    manufacturer = fixture.create("dcim/manufacturers", {"name": marker})
    platform = fixture.create(
        "dcim/platforms",
        {
            "name": marker,
            "manufacturer": manufacturer["id"],
            "network_driver": network_driver,
        },
    )
    device_type = fixture.create(
        "dcim/device-types",
        {"manufacturer": manufacturer["id"], "model": marker},
    )
    role = fixture.create(
        "extras/roles",
        {
            "name": marker,
            "color": "9e9e9e",
            "content_types": [content_types["device"]],
        },
    )
    location_type = fixture.create(
        "dcim/location-types",
        {"name": marker, "content_types": [content_types["device"]]},
    )
    location = fixture.create(
        "dcim/locations",
        {"name": marker, "location_type": location_type["id"], "status": status["id"]},
    )
    for prefix in ("10.0.0.0/24", "192.0.2.0/24"):
        fixture.create(
            "ipam/prefixes",
            {"prefix": prefix, "namespace": namespace["id"], "status": status["id"]},
        )
    device = fixture.create(
        "dcim/devices",
        {
            "name": device_name,
            "serial": marker,
            "device_type": device_type["id"],
            "role": role["id"],
            "location": location["id"],
            "platform": platform["id"],
            "status": status["id"],
            "local_config_context_data": {
                "network_automation": {
                    "bgp": {
                        "local_asn": 65001,
                        "neighbors": [
                            {
                                "address": "192.0.2.1",
                                "remote_asn": 65100,
                                "description": "spine01",
                            },
                            {
                                "address": "192.0.2.3",
                                "remote_asn": 65200,
                                "description": "spine02",
                            },
                        ],
                    }
                }
            },
        },
    )
    for name, interface_type, description, address in (
        ("integration-loop-source", "virtual", "router id", "10.0.0.1/32"),
        ("ethernet-1/1", "100gbase-x-qsfp28", "to spine01", "192.0.2.0/31"),
        ("ethernet-1/2", "100gbase-x-qsfp28", "to spine02", "192.0.2.2/31"),
    ):
        interface = fixture.create(
            "dcim/interfaces",
            {
                "device": device["id"],
                "name": name,
                "type": interface_type,
                "description": description,
                "enabled": True,
                "mgmt_only": False,
                "status": status["id"],
            },
        )
        ip_address = fixture.create(
            "ipam/ip-addresses",
            {"address": address, "namespace": namespace["id"], "status": status["id"]},
        )
        fixture.create(
            "ipam/ip-address-to-interface",
            {"ip_address": ip_address["id"], "interface": interface["id"]},
        )


def create_deployment_devices(fixture: FixtureApi, *, marker: str) -> tuple[str, str]:
    """Create the exact two-node Feature 004 intent and management relationships."""

    content_types = {
        name: fixture.content_type(app, model)
        for name, app, model in (
            ("device", "dcim", "device"),
            ("interface", "dcim", "interface"),
            ("location", "dcim", "location"),
            ("prefix", "ipam", "prefix"),
            ("ipaddress", "ipam", "ipaddress"),
        )
    }
    status = fixture.create(
        "extras/statuses",
        {
            "name": marker,
            "color": "9e9e9e",
            "content_types": list(content_types.values()),
        },
    )
    namespace = fixture.create("ipam/namespaces", {"name": marker})
    manufacturer = fixture.create("dcim/manufacturers", {"name": marker})
    platform = fixture.create(
        "dcim/platforms",
        {
            "name": marker,
            "manufacturer": manufacturer["id"],
            "network_driver": "nokia_srl",
        },
    )
    device_type = fixture.create(
        "dcim/device-types",
        {"manufacturer": manufacturer["id"], "model": marker},
    )
    role = fixture.create(
        "extras/roles",
        {
            "name": marker,
            "color": "9e9e9e",
            "content_types": [content_types["device"]],
        },
    )
    location_type = fixture.create(
        "dcim/location-types",
        {"name": marker, "content_types": [content_types["device"]]},
    )
    location = fixture.create(
        "dcim/locations",
        {"name": marker, "location_type": location_type["id"], "status": status["id"]},
    )
    for prefix in ("10.0.0.0/24", "192.0.2.0/24", "172.31.46.0/24"):
        fixture.create(
            "ipam/prefixes",
            {"prefix": prefix, "namespace": namespace["id"], "status": status["id"]},
        )

    specifications = (
        (
            "f004-spine01",
            65000,
            "10.0.0.1/32",
            "192.0.2.0/31",
            "192.0.2.1",
            65001,
            "172.31.46.11/24",
        ),
        (
            "f004-leaf01",
            65001,
            "10.0.0.2/32",
            "192.0.2.1/31",
            "192.0.2.0",
            65000,
            "172.31.46.12/24",
        ),
    )
    for device_name, local_asn, loopback, link_address, neighbor, remote_asn, management in specifications:
        device = fixture.create(
            "dcim/devices",
            {
                "name": device_name,
                "serial": f"{marker}-{device_name}",
                "device_type": device_type["id"],
                "role": role["id"],
                "location": location["id"],
                "platform": platform["id"],
                "status": status["id"],
                "local_config_context_data": {
                    "network_automation": {
                        "bgp": {
                            "local_asn": local_asn,
                            "neighbors": [
                                {
                                    "address": neighbor,
                                    "remote_asn": remote_asn,
                                    "description": "feature004-peer",
                                }
                            ],
                        }
                    }
                },
            },
        )
        primary_ip_id: object | None = None
        for name, interface_type, description, address, management_only in (
            ("integration-loop-source", "virtual", "router id", loopback, False),
            ("ethernet-1/1", "100gbase-x-qsfp28", "feature004-link", link_address, False),
            ("mgmt0", "virtual", "feature004-management", management, True),
        ):
            interface = fixture.create(
                "dcim/interfaces",
                {
                    "device": device["id"],
                    "name": name,
                    "type": interface_type,
                    "description": description,
                    "enabled": True,
                    "mgmt_only": management_only,
                    "status": status["id"],
                },
            )
            ip_address = fixture.create(
                "ipam/ip-addresses",
                {"address": address, "namespace": namespace["id"], "status": status["id"]},
            )
            fixture.create(
                "ipam/ip-address-to-interface",
                {"ip_address": ip_address["id"], "interface": interface["id"]},
            )
            if management_only:
                primary_ip_id = ip_address["id"]
        assert primary_ip_id is not None
        fixture.update("dcim/devices", device["id"], {"primary_ip4": primary_ip_id})

    return tuple(item[0] for item in specifications)
