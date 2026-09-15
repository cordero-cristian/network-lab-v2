from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pytest


pytestmark = pytest.mark.integration

API_URL = os.environ.get("LAB_UI_API_URL", "http://127.0.0.1:8001").rstrip("/")
UI_URL = os.environ.get("LAB_UI_URL", "http://127.0.0.1:3000").rstrip("/")


def _get(client: httpx.Client, base_url: str, path: str) -> dict[str, Any]:
    response = client.get(f"{base_url}{path}")
    assert response.status_code == 200, f"GET {path} returned {response.status_code}"
    assert response.headers.get("content-type", "").startswith("application/json")
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def test_real_control_plane_reads_and_same_origin_proxy() -> None:
    with httpx.Client(timeout=20) as client:
        started = time.monotonic()
        assert _get(client, API_URL, "/healthz") == {"status": "ok"}
        assert time.monotonic() - started < 1

        overview = _get(client, API_URL, "/api/overview")
        devices = _get(client, API_URL, "/api/devices")
        workflows = _get(client, API_URL, "/api/workflows")
        deployments = _get(client, API_URL, "/api/deployments")
        topology = _get(client, API_URL, "/api/topology")

        assert overview["health"]["overall_status"] in {
            "healthy",
            "degraded",
            "unavailable",
        }
        if devices["availability"]["status"] == "healthy":
            assert devices["count"] == len(devices["items"])
            assert overview["devices"]["total"] == devices["count"]
        if topology["availability"]["status"] == "healthy":
            assert len(topology["nodes"]) == len(devices["items"])

        if devices["items"]:
            device_name = devices["items"][0]["name"]
            detail = _get(client, API_URL, f"/api/devices/{device_name}?live=false")
            assert detail["summary"]["name"] == device_name

        if workflows["items"]:
            workflow = workflows["items"][0]
            workflow_detail = _get(
                client,
                API_URL,
                f"/api/workflows/{workflow['workflow_id']}?run_id={workflow['run_id']}",
            )
            assert workflow_detail["summary"]["run_id"] == workflow["run_id"]

        if deployments["items"]:
            deployment = deployments["items"][0]
            deployment_detail = _get(
                client,
                API_URL,
                f"/api/deployments/{deployment['workflow_id']}?run_id={deployment['run_id']}",
            )
            assert deployment_detail["summary"]["run_id"] == deployment["run_id"]

        retained_failure = next(
            (
                item
                for item in workflows["items"]
                if item["outcome"]
                in {"render_failed", "deployment_failed", "execution_failed"}
            ),
            None,
        )
        if retained_failure is not None:
            failed_detail = _get(
                client,
                API_URL,
                f"/api/workflows/{retained_failure['workflow_id']}?run_id={retained_failure['run_id']}",
            )
            assert failed_detail["failure"] is not None

        assert _get(client, UI_URL, "/healthz") == {"status": "ok"}
        proxied = _get(client, UI_URL, "/api/health")
        assert proxied["overall_status"] in {"healthy", "degraded", "unavailable"}


def test_control_plane_has_no_mutation_surface_or_sensitive_output() -> None:
    paths = (
        "/api/health",
        "/api/overview",
        "/api/devices",
        "/api/workflows",
        "/api/deployments",
        "/api/topology",
    )
    with httpx.Client(timeout=20) as client:
        bodies = []
        for path in paths:
            response = client.get(f"{API_URL}{path}")
            assert response.status_code == 200
            bodies.append(response.text)
            assert client.post(f"{API_URL}{path}", json={}).status_code == 405
        combined = "\n".join(bodies)

    for name in (
        "NAUTOBOT_SUPERUSER_PASSWORD",
        "NAUTOBOT_SUPERUSER_API_TOKEN",
        "LAB_DEVICE_PASSWORD",
    ):
        value = os.environ.get(name)
        if value and value in combined:
            pytest.fail(f"sensitive environment value from {name} appeared in API output")
    for forbidden in ("set /", "authorization", "traceback", "/app/artifacts"):
        assert forbidden not in combined.lower()
