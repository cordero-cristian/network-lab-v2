from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FEATURE_001_SERVICES = {
    "kafka",
    "nautobot",
    "nautobot-init",
    "nautobot-scheduler",
    "nautobot-worker",
    "postgres",
    "redis",
    "temporal",
    "temporal-schema",
    "temporal-ui",
}
AUTOMATION_SERVICES = {"automation-worker", "event-consumer"}
TEST_ENVIRONMENT = {
    "COMPOSE_PROJECT_NAME": "network-lab-static-test",
    "KAFKA_CLUSTER_ID": "MkU3OEVBNTcwNTJENDM2Qk",
    "LAB_KAFKA_HOST_PORT": "9092",
    "LAB_NAUTOBOT_HOST_PORT": "8000",
    "LAB_TEMPORAL_HOST_PORT": "7233",
    "LAB_TEMPORAL_UI_HOST_PORT": "8080",
    "NAUTOBOT_DB_PASSWORD": "static-test",
    "NAUTOBOT_SECRET_KEY": "static-test",
    "NAUTOBOT_SUPERUSER_API_TOKEN": "0" * 40,
    "NAUTOBOT_SUPERUSER_PASSWORD": "static-test",
    "POSTGRES_ADMIN_PASSWORD": "static-test",
    "REDIS_PASSWORD": "static-test",
    "TEMPORAL_DB_PASSWORD": "static-test",
}


@pytest.fixture(scope="module")
def compose_config() -> dict[str, Any]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--file",
            str(REPOSITORY_ROOT / "compose.yaml"),
            "--profile",
            "*",
            "config",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ | TEST_ENVIRONMENT,
    )
    return json.loads(result.stdout)


def test_automation_profile_adds_exactly_two_application_services(
    compose_config: dict[str, Any],
) -> None:
    services = compose_config["services"]
    automation = {
        name
        for name, service in services.items()
        if service.get("profiles") == ["automation"]
    }

    assert automation == AUTOMATION_SERVICES
    assert {name for name, service in services.items() if not service.get("profiles")} == (
        FEATURE_001_SERVICES
    )
    assert services["temporal-namespace"]["profiles"] == ["init"]
    assert set(services) == FEATURE_001_SERVICES | AUTOMATION_SERVICES | {
        "temporal-namespace"
    }
    assert set(compose_config["volumes"]) == {
        "kafka-data",
        "nautobot-media",
        "postgres-data",
    }
    assert set(compose_config["networks"]) == {"default"}


def test_automation_services_share_one_pinned_application_build(
    compose_config: dict[str, Any],
) -> None:
    services = compose_config["services"]
    worker = services["automation-worker"]
    consumer = services["event-consumer"]

    assert worker["image"] == consumer["image"]
    image_version = worker["image"].rsplit("/", 1)[-1]
    assert ":" in image_version or "@sha256:" in worker["image"]
    assert not image_version.endswith(":latest")
    assert "build" not in consumer
    assert Path(worker["build"]["context"]).resolve() == REPOSITORY_ROOT
    assert Path(worker["build"]["dockerfile"]).name == "Dockerfile.automation"

    dockerfile = (REPOSITORY_ROOT / "Dockerfile.automation").read_text(encoding="ascii")
    from_lines = [
        line.split("#", 1)[0].strip()
        for line in dockerfile.splitlines()
        if line.lstrip().upper().startswith("FROM ")
    ]
    assert any("3.12.13" in line for line in from_lines)
    assert "0.11.28" in dockerfile
    assert all(":latest" not in line for line in from_lines)


def test_automation_processes_have_only_required_runtime_access(
    compose_config: dict[str, Any],
) -> None:
    services = compose_config["services"]
    worker = services["automation-worker"]
    consumer = services["event-consumer"]

    assert worker["command"] == ["network-worker"]
    assert consumer["command"] == ["network-event-consumer"]
    assert not worker.get("ports")
    assert not consumer.get("ports")

    expected_endpoints = {
        "LAB_KAFKA_BOOTSTRAP_SERVERS": "kafka:29092",
        "LAB_TEMPORAL_ADDRESS": "temporal:7233",
    }
    for service in (worker, consumer):
        assert expected_endpoints.items() <= service["environment"].items()

    assert worker["environment"]["LAB_NAUTOBOT_URL"] == "http://nautobot:8080"
    assert "LAB_NAUTOBOT_URL" not in consumer["environment"]
    assert consumer["environment"]["NAUTOBOT_SUPERUSER_API_TOKEN"] == "unused-by-consumer"

    assert not consumer.get("volumes")
    assert len(worker["volumes"]) == 1
    artifact_mount = worker["volumes"][0]
    assert artifact_mount["type"] == "bind"
    assert Path(artifact_mount["source"]).resolve() == REPOSITORY_ROOT / "artifacts"
    assert artifact_mount["target"] == "/app/artifacts"
    assert not artifact_mount.get("read_only", False)


def test_automation_dependencies_require_healthy_internal_services(
    compose_config: dict[str, Any],
) -> None:
    services = compose_config["services"]

    assert services["automation-worker"]["depends_on"] == {
        name: {"condition": "service_healthy", "required": True}
        for name in ("kafka", "nautobot", "temporal")
    }
    assert services["event-consumer"]["depends_on"] == {
        name: {"condition": "service_healthy", "required": True}
        for name in ("kafka", "temporal")
    }


@pytest.mark.parametrize("service_name", sorted(AUTOMATION_SERVICES))
def test_automation_healthchecks_require_fresh_process_heartbeats(
    compose_config: dict[str, Any], service_name: str
) -> None:
    healthcheck = compose_config["services"][service_name]["healthcheck"]
    command = " ".join(healthcheck["test"]).lower()

    assert healthcheck["test"][0] == "CMD-SHELL"
    assert "test -f" in command and "ready" in command
    assert "find " in command and "heartbeat" in command and "-mmin -1" in command
    assert healthcheck["interval"].endswith("s")
    assert healthcheck["timeout"].endswith("s")
    assert healthcheck["start_period"].endswith("s")
    assert healthcheck["retries"] > 0
