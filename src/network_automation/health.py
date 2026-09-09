"""Application-level readiness checks for the local supporting lab."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import httpx
from confluent_kafka.admin import AdminClient
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
from temporalio.client import Client

from network_automation.settings import LabSettings

RUNTIME_SERVICES = {
    "postgres",
    "redis",
    "kafka",
    "temporal",
    "temporal-ui",
    "nautobot",
    "nautobot-worker",
    "nautobot-scheduler",
}
INITIALIZERS = {"temporal-schema", "temporal-namespace", "nautobot-init"}
AGGREGATE_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _result(name: str, operation: Callable[[], str]) -> CheckResult:
    try:
        return CheckResult(name, True, operation())
    except Exception as exc:  # Every boundary reports a named failure.
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}")


def _compose_rows(settings: LabSettings) -> list[dict[str, object]]:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            settings.compose_project,
            "ps",
            "--all",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=settings.probe_timeout_seconds,
    )
    output = completed.stdout.strip()
    if not output:
        return []
    try:
        parsed = json.loads(output)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return [json.loads(line) for line in output.splitlines() if line.strip()]


def check_compose_services(settings: LabSettings) -> list[CheckResult]:
    try:
        rows = _compose_rows(settings)
    except Exception as exc:
        return [CheckResult("compose", False, f"{type(exc).__name__}: {exc}")]

    by_service = {str(row.get("Service")): row for row in rows}
    results: list[CheckResult] = []
    for service in sorted(RUNTIME_SERVICES):
        if service not in by_service:
            results.append(CheckResult(service, False, "container missing"))
        else:
            row = by_service[service]
            state = str(row.get("State", "")).lower()
            health_state = str(row.get("Health", "")).lower()
            ok = state == "running" and health_state == "healthy"
            results.append(
                CheckResult(
                    service,
                    ok,
                    f"state={state or 'unknown'} health={health_state or 'unknown'}",
                )
            )
    for service in sorted(INITIALIZERS):
        if service not in by_service:
            results.append(CheckResult(service, False, "container missing"))
        else:
            row = by_service[service]
            state = str(row.get("State", "")).lower()
            exit_code = int(row.get("ExitCode", -1))
            results.append(
                CheckResult(
                    service,
                    state == "exited" and exit_code == 0,
                    f"state={state or 'unknown'} exit={exit_code}",
                )
            )
    return results


def check_compose(settings: LabSettings) -> CheckResult:
    results = check_compose_services(settings)
    failures = [f"{result.name} {result.detail}" for result in results if not result.ok]
    if failures:
        return CheckResult("compose", False, "; ".join(failures))
    return CheckResult("compose", True, "all services and initializers ready")


def check_nautobot(settings: LabSettings) -> CheckResult:
    def operation() -> str:
        base = str(settings.nautobot_url).rstrip("/")
        deadline = time.monotonic() + settings.probe_timeout_seconds
        with httpx.Client() as client:
            health = client.get(f"{base}/health/", timeout=max(deadline - time.monotonic(), 0.001))
            health.raise_for_status()
            status = client.get(
                f"{base}/api/status/",
                headers={"Authorization": f"Token {settings.nautobot_token.get_secret_value()}"},
                timeout=max(deadline - time.monotonic(), 0.001),
            )
            status.raise_for_status()
        return "health endpoint and authenticated API responded"

    return _result("nautobot", operation)


def check_kafka(settings: LabSettings) -> CheckResult:
    def operation() -> str:
        metadata = AdminClient(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "socket.timeout.ms": settings.probe_timeout_seconds * 1000,
            }
        ).list_topics(timeout=settings.probe_timeout_seconds)
        if not metadata.brokers:
            raise RuntimeError("broker metadata contained no brokers")
        brokers = ", ".join(
            f"{broker.host}:{broker.port}" for broker in metadata.brokers.values()
        )
        return f"broker metadata reachable ({brokers})"

    return _result("kafka", operation)


async def check_temporal(settings: LabSettings) -> CheckResult:
    async def operation() -> str:
        client = await Client.connect(
            settings.temporal_address, namespace=settings.temporal_namespace
        )
        serving = await client.service_client.check_health()
        if not serving:
            raise RuntimeError("RPC health did not report SERVING")
        await client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=settings.temporal_namespace)
        )
        return f"RPC SERVING; namespace {settings.temporal_namespace!r} exists"

    try:
        detail = await asyncio.wait_for(operation(), timeout=settings.probe_timeout_seconds)
        return CheckResult("temporal", True, detail)
    except Exception as exc:
        return CheckResult("temporal", False, f"{type(exc).__name__}: {exc}")


def check_temporal_ui(settings: LabSettings) -> CheckResult:
    def operation() -> str:
        response = httpx.get(
            f"{str(settings.temporal_ui_url).rstrip('/')}/api/v1/namespaces",
            timeout=settings.probe_timeout_seconds,
        )
        response.raise_for_status()
        if not response.json().get("namespaces"):
            raise RuntimeError("UI backend returned no namespaces")
        return "HTTP endpoint and Temporal-backed namespace API responded"

    return _result("temporal-ui", operation)


def _redact(results: Iterable[CheckResult], settings: LabSettings) -> list[CheckResult]:
    secrets = (
        settings.nautobot_password.get_secret_value(),
        settings.nautobot_token.get_secret_value(),
    )
    redacted: list[CheckResult] = []
    for result in results:
        detail = result.detail
        for secret in secrets:
            if secret:
                detail = detail.replace(secret, "***")
        redacted.append(CheckResult(result.name, result.ok, detail))
    return redacted


async def run_checks(settings: LabSettings) -> list[CheckResult]:
    compose_results, nautobot, kafka, temporal, temporal_ui = await asyncio.gather(
        asyncio.to_thread(check_compose_services, settings),
        asyncio.to_thread(check_nautobot, settings),
        asyncio.to_thread(check_kafka, settings),
        check_temporal(settings),
        asyncio.to_thread(check_temporal_ui, settings),
    )
    results = [*compose_results, nautobot, kafka, temporal, temporal_ui]
    return _redact(results, settings)


def main() -> int:
    try:
        settings = LabSettings()
        results = asyncio.run(
            asyncio.wait_for(run_checks(settings), timeout=AGGREGATE_TIMEOUT_SECONDS)
        )
    except Exception as exc:
        print(f"FAIL settings: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    for result in results:
        print(f"{'PASS' if result.ok else 'FAIL'} {result.name}: {result.detail}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
