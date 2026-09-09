from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from network_automation.intent.nautobot import NautobotClient, device_intent_from_nautobot
from network_automation.rendering.srlinux import render_srlinux, write_srlinux_artifact
from network_automation.settings import LabSettings

pytestmark = pytest.mark.integration


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

    def cleanup(self) -> None:
        failures: list[str] = []
        for endpoint, object_id in reversed(self.created):
            response = self.client.delete(f"{self.base_url}{endpoint}/{object_id}/")
            if response.status_code not in {204, 404}:
                failures.append(f"{endpoint}/{object_id}: HTTP {response.status_code}")
                continue
            verification = self.client.get(f"{self.base_url}{endpoint}/{object_id}/")
            if verification.status_code != 404:
                failures.append(
                    f"{endpoint}/{object_id}: still present (HTTP {verification.status_code})"
                )
        assert not failures, f"fixture cleanup failures: {failures}"


def test_real_nautobot_intent_to_unique_artifact(tmp_path: Path) -> None:
    settings = LabSettings()
    fixture = FixtureApi(settings)
    suffix = uuid4().hex[:10]
    marker = f"feature002-{suffix}"
    device_name = f"feature002-leaf-{suffix}"

    try:
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
            {"name": marker, "color": "9e9e9e", "content_types": [content_types["device"]]},
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
                                {"address": "192.0.2.1", "remote_asn": 65100, "description": "spine01"},
                                {"address": "192.0.2.3", "remote_asn": 65200, "description": "spine02"},
                            ],
                        }
                    }
                },
            },
        )

        interface_specs = (
            ("integration-loop-source", "virtual", "router id", "10.0.0.1/32"),
            ("ethernet-1/1", "100gbase-x-qsfp28", "to spine01", "192.0.2.0/31"),
            ("ethernet-1/2", "100gbase-x-qsfp28", "to spine02", "192.0.2.2/31"),
        )
        for name, interface_type, description, address in interface_specs:
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

        with NautobotClient(
            str(settings.nautobot_url),
            settings.nautobot_token.get_secret_value(),
            timeout=settings.probe_timeout_seconds,
        ) as client:
            raw = client.get_device_data(device_name)
        intent = device_intent_from_nautobot(raw)
        first = render_srlinux(intent)
        second = render_srlinux(intent)
        artifact = write_srlinux_artifact(intent, tmp_path)

        assert intent.name == device_name
        assert intent.platform == "nokia_srl"
        assert not hasattr(intent.loopback, "name")
        assert first == second == artifact.read_text()
        assert artifact == tmp_path / f"{device_name}.cfg"
        assert first.startswith(f"set / system name host-name {device_name}\n")
        assert "set / interface system0 subinterface 0 ipv4 address 10.0.0.1/32\n" in first
        assert "protocols bgp autonomous-system 65001\n" in first
    finally:
        try:
            fixture.cleanup()
        finally:
            fixture.close()
