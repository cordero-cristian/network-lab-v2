from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from network_automation.settings import LabSettings
from tests.integration.support.nautobot_fixture import (
    FixtureApi,
    create_deployment_devices,
)


pytestmark = pytest.mark.integration


def test_real_current_comparison_is_read_only_and_source_aware() -> None:
    settings = LabSettings()
    fixture = FixtureApi(settings)
    marker = f"feature007-{uuid4().hex[:12]}"
    api_url = "http://127.0.0.1:8001"

    try:
        assert create_deployment_devices(fixture, marker=marker) == (
            "f004-spine01",
            "f004-leaf01",
        )
        with httpx.Client(timeout=20) as client:
            live_response = client.get(
                f"{api_url}/api/devices/f004-leaf01", params={"live": "true"}
            )
            assert live_response.status_code == 200
            live = live_response.json()

            assert "live_state" not in live
            assert live["configuration_drift"]["status"] == "in_sync"
            assert live["configuration_drift"]["result"]["mismatches"] == 0
            assert live["operational_health"]["status"] in {"healthy", "degraded"}
            assert live["operational_health"]["result"] is not None
            assert live["configuration_drift"]["sources"]["intent"]["status"] == "healthy"
            assert live["configuration_drift"]["sources"]["device"]["status"] == "healthy"
            assert live["configuration_drift"]["observed_at"] == live["operational_health"]["observed_at"]
            assert live["configuration_drift"]["result"]["observed_at"] == live["operational_health"]["result"]["observed_at"]

            not_requested = client.get(
                f"{api_url}/api/devices/f004-leaf01", params={"live": "false"}
            ).json()
            assert not_requested["configuration_drift"]["status"] == "unavailable"
            assert not_requested["operational_health"]["status"] == "unavailable"
            assert not_requested["configuration_drift"]["sources"]["device"]["code"] == "not_configured"
    finally:
        fixture.cleanup()
        fixture.close()
