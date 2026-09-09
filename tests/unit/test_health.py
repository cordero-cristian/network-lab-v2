from __future__ import annotations

import asyncio
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from network_automation import health
from network_automation.health import CheckResult
from network_automation.settings import LabSettings


@pytest.fixture
def settings() -> LabSettings:
    return LabSettings(
        _env_file=None,
        nautobot_password="not-printed-password",
        nautobot_token="not-printed-token",
    )


def compose_row(service: str, *, state: str, health_state: str = "", exit_code: int = 0) -> dict[str, object]:
    return {
        "Service": service,
        "State": state,
        "Health": health_state,
        "ExitCode": exit_code,
    }


def test_compose_requires_healthy_runtime_and_successful_initializers(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    rows = [compose_row(name, state="running", health_state="healthy") for name in health.RUNTIME_SERVICES]
    rows.extend(compose_row(name, state="exited") for name in health.INITIALIZERS)
    monkeypatch.setattr(health, "_compose_rows", lambda _: rows)

    assert health.check_compose(settings).ok


@pytest.mark.parametrize("initializer", sorted(health.INITIALIZERS))
def test_compose_reports_initializer_failure(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings, initializer: str
) -> None:
    rows = [compose_row(name, state="running", health_state="healthy") for name in health.RUNTIME_SERVICES]
    rows.extend(
        compose_row(name, state="exited", exit_code=1 if name == initializer else 0)
        for name in health.INITIALIZERS
    )
    monkeypatch.setattr(health, "_compose_rows", lambda _: rows)

    result = health.check_compose(settings)

    assert not result.ok
    assert initializer in result.detail


def test_compose_reports_missing_and_unhealthy_services(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    monkeypatch.setattr(
        health,
        "_compose_rows",
        lambda _: [compose_row("postgres", state="running", health_state="unhealthy")],
    )

    result = health.check_compose(settings)

    assert not result.ok
    assert "container missing" in result.detail


def test_compose_subprocess_is_bounded_and_not_shell_interpolated(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    seen: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["args"] = args
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 0, "[]", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    health._compose_rows(settings)

    assert seen["timeout"] == 10
    assert seen["args"] == [
        "docker", "compose", "--project-name", "network-lab", "ps", "--all", "--format", "json"
    ]


def test_nautobot_reports_authenticated_api_failure(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        status = 401 if request.url.path == "/api/status/" else 200
        return httpx.Response(status, request=request)

    client_class = httpx.Client
    monkeypatch.setattr(
        health.httpx,
        "Client",
        lambda: client_class(transport=httpx.MockTransport(handler)),
    )

    result = health.check_nautobot(settings)

    assert not result.ok
    assert "401" in result.detail


def test_nautobot_uses_one_deadline_for_both_requests(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    timeouts: list[float] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

    class Client:
        def __enter__(self) -> Client:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def get(self, _: str, **kwargs: object) -> Response:
            timeouts.append(float(kwargs["timeout"]))
            return Response()

    times = iter([0.0, 0.2, 0.9])
    monkeypatch.setattr(health.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(health.httpx, "Client", Client)

    assert health.check_nautobot(settings).ok
    assert timeouts == pytest.approx([9.8, 9.1])


def test_kafka_reports_metadata_failure(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    class EmptyAdminClient:
        def __init__(self, _: object) -> None:
            pass

        def list_topics(self, *, timeout: int) -> SimpleNamespace:
            assert timeout == settings.probe_timeout_seconds
            return SimpleNamespace(brokers={})

    monkeypatch.setattr(health, "AdminClient", EmptyAdminClient)

    result = health.check_kafka(settings)

    assert not result.ok
    assert "no brokers" in result.detail


def test_temporal_reports_rpc_failure(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    async def failed_connect(*_: object, **__: object) -> object:
        raise ConnectionError("RPC unavailable")

    monkeypatch.setattr(health.Client, "connect", failed_connect)

    result = asyncio.run(health.check_temporal(settings))

    assert not result.ok
    assert "RPC unavailable" in result.detail


def test_temporal_ui_requires_backend_namespaces(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"namespaces": []}, request=request)

    monkeypatch.setattr(
        health.httpx,
        "get",
        lambda url, timeout: httpx.Client(transport=httpx.MockTransport(handler)).get(
            url, timeout=timeout
        ),
    )

    result = health.check_temporal_ui(settings)

    assert not result.ok
    assert "no namespaces" in result.detail


def test_all_boundaries_are_reported_and_secrets_redacted(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    monkeypatch.setattr(
        health, "check_compose_services", lambda _: [CheckResult("compose", True, "ok")]
    )
    monkeypatch.setattr(
        health,
        "check_nautobot",
        lambda _: CheckResult("nautobot", False, "not-printed-password not-printed-token"),
    )
    monkeypatch.setattr(health, "check_kafka", lambda _: CheckResult("kafka", True, "ok"))

    async def temporal(_: LabSettings) -> CheckResult:
        return CheckResult("temporal", True, "ok")

    monkeypatch.setattr(health, "check_temporal", temporal)
    monkeypatch.setattr(health, "check_temporal_ui", lambda _: CheckResult("temporal-ui", True, "ok"))

    results = asyncio.run(health.run_checks(settings))

    assert [result.name for result in results][-4:] == [
        "nautobot", "kafka", "temporal", "temporal-ui"
    ]
    assert "not-printed" not in " ".join(result.detail for result in results)


def test_main_returns_failure_without_stopping_after_first_failed_probe(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    async def failed(_: LabSettings) -> list[CheckResult]:
        return [CheckResult("compose", False, "down"), CheckResult("kafka", True, "ok")]

    monkeypatch.setattr(health, "LabSettings", lambda: settings)
    monkeypatch.setattr(health, "run_checks", failed)

    assert health.main() == 1


def test_main_enforces_aggregate_timeout(
    monkeypatch: pytest.MonkeyPatch, settings: LabSettings
) -> None:
    async def slow(_: LabSettings) -> list[CheckResult]:
        await asyncio.sleep(1)
        return []

    monkeypatch.setattr(health, "LabSettings", lambda: settings)
    monkeypatch.setattr(health, "run_checks", slow)
    monkeypatch.setattr(health, "AGGREGATE_TIMEOUT_SECONDS", 0.001)

    assert health.main() == 1
