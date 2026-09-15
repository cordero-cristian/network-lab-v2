from fastapi.testclient import TestClient

from network_automation.api.app import create_app
from network_automation.intent.nautobot import NautobotError
from network_automation.settings import LabSettings
from tests.unit.test_api_devices import LogicalNautobot


def settings() -> LabSettings:
    return LabSettings(_env_file=None, nautobot_password="password", nautobot_token="token")


class EmptyTemporal:
    async def list_workflows(self, **kwargs):
        if False:
            yield None


def test_device_detail_distinguishes_temporal_outage_from_empty_history() -> None:
    unavailable_app = create_app(
        settings=settings(), nautobot_client=LogicalNautobot(), temporal_client=None
    )
    empty_app = create_app(
        settings=settings(), nautobot_client=LogicalNautobot(), temporal_client=EmptyTemporal()
    )

    with TestClient(unavailable_app) as client:
        unavailable = client.get("/api/devices/leaf01").json()
    with TestClient(empty_app) as client:
        empty = client.get("/api/devices/leaf01").json()

    assert unavailable["summary"]["validation_status"] == "unavailable"
    assert unavailable["latest_deployment"]["availability"]["status"] == "unavailable"
    assert unavailable["latest_deployment"]["availability"]["code"] == "unreachable"
    assert empty["summary"]["validation_status"] == "unknown"
    assert empty["latest_deployment"]["availability"]["status"] == "unknown"
    assert empty["latest_deployment"]["availability"]["code"] == "history_unavailable"


def test_actual_nautobot_list_failure_is_section_unavailable() -> None:
    class FailedNautobot:
        def list_inventory_devices(self, *, limit: int):
            raise NautobotError("safe upstream failure")

    app = create_app(
        settings=settings(), nautobot_client=FailedNautobot(), temporal_client=None
    )
    with TestClient(app) as client:
        response = client.get("/api/devices")

    assert response.status_code == 200
    assert response.json()["availability"]["status"] == "unavailable"
    assert response.json()["availability"]["code"] == "unreachable"
