from pathlib import Path

from fastapi.testclient import TestClient

from network_automation.api.app import create_app
from network_automation.settings import LabSettings


class EmptyNautobot:
    def list_inventory_devices(self, *, limit: int):
        return ()

    def list_topology_interfaces(self, devices):
        return ()


def settings() -> LabSettings:
    return LabSettings(
        _env_file=None, nautobot_password="password-value", nautobot_token="token-value"
    )


def test_routes_are_read_only_and_api_responses_are_no_store() -> None:
    app = create_app(settings=settings(), nautobot_client=EmptyNautobot(), temporal_client=None)
    methods = {method for route in app.routes for method in (route.methods or set())}

    assert methods <= {"GET", "HEAD"}
    with TestClient(app) as client:
        response = client.get("/api/devices")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/api/devices").status_code == 405


def test_validation_errors_are_static_and_do_not_reflect_input() -> None:
    app = create_app(settings=settings(), nautobot_client=EmptyNautobot(), temporal_client=None)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/devices/not/a/device")
        invalid = client.get("/api/workflows", params={"limit": "password-value"})

    assert response.status_code == 404
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_request"
    assert "password-value" not in invalid.text


def test_api_source_has_no_mutation_integration_imports() -> None:
    api_root = Path(__file__).parents[2] / "src/network_automation/api"
    source = "\n".join(path.read_text() for path in api_root.glob("*.py"))

    assert "events.producer" not in source
    assert "activities.deployment" not in source
    assert "start_workflow" not in source
    assert "_write_srlinux_artifact" not in source
    assert ".deploy(" not in source
    assert ".set(" not in source
    assert "SRLinuxClient" not in source
    assert "devices.srlinux" not in source

    read_boundary = (
        Path(__file__).parents[2]
        / "src/network_automation/devices/read_state.py"
    ).read_text()
    assert "read_native_state" in read_boundary
    assert ".deploy(" not in read_boundary
    assert ".set(" not in read_boundary


def test_temporal_connection_recovers_after_startup_failure(monkeypatch) -> None:
    calls = 0

    class RecoveredTemporal:
        async def list_workflows(self, **kwargs):
            if False:
                yield None

    async def connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("not ready")
        return RecoveredTemporal()

    monkeypatch.setattr(create_app.__globals__["Client"], "connect", connect)
    app = create_app(settings=settings(), nautobot_client=EmptyNautobot())
    with TestClient(app) as client:
        response = client.get("/api/workflows")

    assert response.status_code == 200
    assert response.json()["availability"]["status"] == "healthy"
    assert calls == 2


def test_programming_failure_reaches_sanitized_500(monkeypatch) -> None:
    async def broken_projection(*args, **kwargs):
        raise ValueError("secret internal model defect")

    monkeypatch.setitem(create_app.__globals__, "list_devices", broken_projection)
    app = create_app(
        settings=settings(), nautobot_client=EmptyNautobot(), temporal_client=None
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/devices")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret internal model defect" not in response.text
