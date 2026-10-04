from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from network_automation.api.devices import get_topology
from network_automation.intent.nautobot import NautobotClient
from network_automation.settings import LabSettings


pytestmark = pytest.mark.integration
API_ACCEPT = "application/json; version=3.2"


def test_migrated_api_identity_depth_and_version() -> None:
    settings = LabSettings()
    base_url = str(settings.nautobot_url).rstrip("/")
    headers = {
        "Authorization": f"Token {settings.nautobot_token.get_secret_value()}",
        "Accept": API_ACCEPT,
    }

    with httpx.Client(headers=headers, timeout=settings.probe_timeout_seconds) as client:
        status = client.get(f"{base_url}/api/status/")
        status.raise_for_status()
        assert status.headers["API-Version"] == "3.2"
        assert status.json()["nautobot-version"] == "3.2.5"

        users = client.get(
            f"{base_url}/api/users/users/",
            params={
                "username": os.environ.get("NAUTOBOT_SUPERUSER_NAME", "admin"),
                "depth": 1,
            },
        )
        users.raise_for_status()
        user_results = users.json()["results"]
        assert len(user_results) == 1
        assert user_results[0]["is_superuser"] is True

        devices = client.get(
            f"{base_url}/api/dcim/devices/", params={"depth": 1, "limit": 100}
        )
        devices.raise_for_status()
        device_results = devices.json()["results"]
        assert device_results
        for field in ("role", "platform", "status"):
            relation = device_results[0][field]
            assert isinstance(relation, dict)
            assert relation["id"]
            assert relation["display"]


def test_retained_cable_endpoints_remain_reciprocal_and_visible() -> None:
    settings = LabSettings()
    with NautobotClient(
        str(settings.nautobot_url),
        settings.nautobot_token.get_secret_value(),
        timeout=settings.probe_timeout_seconds,
    ) as client:
        devices = client.list_inventory_devices(limit=100)
        interfaces = client.list_topology_interfaces(devices)
        endpoints = {
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
        assert any(
            (remote_device, remote_interface, device, interface) in endpoints
            for device, interface, remote_device, remote_interface in endpoints
        )

        topology = asyncio.run(
            get_topology(client, inventory_devices=devices)
        )

    assert any(link.kind == "physical" for link in topology.links)
