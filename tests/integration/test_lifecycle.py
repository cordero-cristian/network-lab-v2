from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import uuid
from urllib.parse import urlparse

import httpx
import pytest
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from google.protobuf.duration_pb2 import Duration
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    RegisterNamespaceRequest,
)
from temporalio.client import Client
from temporalio.service import RPCError

from network_automation.settings import LabSettings

pytestmark = [pytest.mark.integration, pytest.mark.lifecycle]


def unused_ports(count: int, forbidden: set[int]) -> list[int]:
    sockets: list[socket.socket] = []
    try:
        while len(sockets) < count:
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            if int(sock.getsockname()[1]) in forbidden:
                sock.close()
                continue
            sockets.append(sock)
        return [int(sock.getsockname()[1]) for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def compose(
    project: str,
    *args: str,
    timeout: int = 660,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "--project-name", project, *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def start(project: str) -> None:
    compose(project, "up", "-d", "--wait", "--wait-timeout", "600")
    compose(
        project,
        "--profile",
        "init",
        "up",
        "--no-deps",
        "--force-recreate",
        "--exit-code-from",
        "temporal-namespace",
        "temporal-namespace",
        timeout=120,
    )


async def create_temporal_namespace(settings: LabSettings, namespace: str) -> None:
    client = await asyncio.wait_for(
        Client.connect(settings.temporal_address), timeout=settings.probe_timeout_seconds
    )
    await asyncio.wait_for(
        client.workflow_service.register_namespace(
            RegisterNamespaceRequest(
                namespace=namespace,
                workflow_execution_retention_period=Duration(seconds=86400),
            )
        ),
        timeout=settings.probe_timeout_seconds,
    )


async def assert_temporal_namespace(settings: LabSettings, namespace: str) -> None:
    client = await asyncio.wait_for(
        Client.connect(settings.temporal_address), timeout=settings.probe_timeout_seconds
    )
    described = await asyncio.wait_for(
        client.workflow_service.describe_namespace(DescribeNamespaceRequest(namespace=namespace)),
        timeout=settings.probe_timeout_seconds,
    )
    assert described.namespace_info.name == namespace


def test_disposable_lifecycle_retains_state_and_reports_dependency_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.getenv("LAB_RUN_LIFECYCLE") != "1":
        pytest.fail("set LAB_RUN_LIFECYCLE=1 to authorize the isolated lifecycle test")

    project = os.environ.get("LAB_COMPOSE_PROJECT") or f"network-lab-test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("LAB_COMPOSE_PROJECT", project)
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    assert project.startswith("network-lab-test-")
    assert project != "network-lab"
    assert os.environ.get("COMPOSE_PROJECT_NAME") == project

    endpoints = {
        "NAUTOBOT": "http://localhost:{port}",
        "TEMPORAL": "localhost:{port}",
        "TEMPORAL_UI": "http://localhost:{port}",
        "KAFKA": "localhost:{port}",
    }
    endpoint_names = {
        "NAUTOBOT": "LAB_NAUTOBOT_URL",
        "TEMPORAL": "LAB_TEMPORAL_ADDRESS",
        "TEMPORAL_UI": "LAB_TEMPORAL_UI_URL",
        "KAFKA": "LAB_KAFKA_BOOTSTRAP_SERVERS",
    }
    provided_ports = [
        int(value)
        for service in endpoints
        if (value := os.environ.get(f"LAB_{service}_HOST_PORT"))
    ]
    generated_ports = iter(
        unused_ports(len(endpoints) - len(provided_ports), set(provided_ports))
    )
    for service, template in endpoints.items():
        port_name = f"LAB_{service}_HOST_PORT"
        port = int(os.environ.get(port_name) or next(generated_ports))
        monkeypatch.setenv(port_name, str(port))
        monkeypatch.setenv(endpoint_names[service], template.format(port=port))

    settings = LabSettings()
    nautobot_port = urlparse(str(settings.nautobot_url)).port
    temporal_ui_port = urlparse(str(settings.temporal_ui_url)).port
    temporal_port = int(settings.temporal_address.rsplit(":", 1)[1])
    kafka_servers = settings.kafka_bootstrap_servers or ""
    assert nautobot_port == int(os.environ["LAB_NAUTOBOT_HOST_PORT"])
    assert temporal_ui_port == int(os.environ["LAB_TEMPORAL_UI_HOST_PORT"])
    assert temporal_port == int(os.environ["LAB_TEMPORAL_HOST_PORT"])
    assert kafka_servers == f"localhost:{os.environ['LAB_KAFKA_HOST_PORT']}"
    assert len({nautobot_port, temporal_ui_port, temporal_port, settings.kafka_host_port}) == 4
    assert {nautobot_port, temporal_ui_port, temporal_port, settings.kafka_host_port}.isdisjoint(
        {8000, 8080, 7233, 9092}
    )
    run_id = uuid.uuid4().hex
    tag_name = f"network-lab-lifecycle-{run_id}"
    topic = f"network-lab-lifecycle-{run_id}"
    namespace = f"network-lab-lifecycle-{run_id}"
    payload = run_id.encode()
    tag_url: str | None = None
    collision_project = f"{project}-collision"

    compose(project, "config", "--quiet", timeout=30)
    try:
        start(project)
        start(project)

        admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
        metadata = admin.list_topics(timeout=settings.probe_timeout_seconds)
        assert any(
            broker.port == settings.kafka_host_port for broker in metadata.brokers.values()
        )

        headers = {"Authorization": f"Token {settings.nautobot_token.get_secret_value()}"}
        response = httpx.post(
            f"{str(settings.nautobot_url).rstrip('/')}/api/extras/tags/",
            headers=headers,
            json={"name": tag_name, "color": "abcdef", "content_types": []},
            timeout=settings.probe_timeout_seconds,
        )
        response.raise_for_status()
        tag_url = response.json()["url"]

        admin.create_topics(
            [NewTopic(topic, num_partitions=1, replication_factor=1)]
        )[topic].result(settings.probe_timeout_seconds)
        producer = Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "allow.auto.create.topics": False,
            }
        )
        producer.produce(topic, payload)
        assert producer.flush(settings.probe_timeout_seconds) == 0
        del producer
        asyncio.run(create_temporal_namespace(settings, namespace))

        compose(project, "down", timeout=120)
        start(project)

        response = httpx.get(tag_url, headers=headers, timeout=settings.probe_timeout_seconds)
        response.raise_for_status()
        assert response.json()["name"] == tag_name

        consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": f"lifecycle-{run_id}",
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([topic])
        try:
            message = consumer.poll(settings.probe_timeout_seconds)
            assert message is not None and message.error() is None
            assert message.value() == payload
        finally:
            consumer.close()
        asyncio.run(assert_temporal_namespace(settings, namespace))

        collision = compose(
            collision_project,
            "up",
            "-d",
            "kafka",
            timeout=120,
            check=False,
        )
        assert collision.returncode != 0
        assert "port" in (collision.stdout + collision.stderr).lower()
        compose(collision_project, "down", "--volumes", "--remove-orphans", timeout=120)

        failed_namespace_env = os.environ.copy()
        failed_namespace_env["LAB_TEMPORAL_NAMESPACE_ADDRESS"] = "missing-temporal:7233"
        namespace_failure = compose(
            project,
            "--profile",
            "init",
            "up",
            "--no-deps",
            "--force-recreate",
            "--exit-code-from",
            "temporal-namespace",
            "temporal-namespace",
            timeout=120,
            check=False,
            env=failed_namespace_env,
        )
        assert namespace_failure.returncode != 0
        running = compose(project, "ps", "--status", "running", "--services", timeout=30)
        assert "temporal-ui" in running.stdout.splitlines()
        unhealthy_namespace = subprocess.run(
            ["uv", "run", "network-lab-check"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert unhealthy_namespace.returncode != 0
        assert "temporal-namespace" in (
            unhealthy_namespace.stdout + unhealthy_namespace.stderr
        )
        compose(
            project,
            "--profile",
            "init",
            "up",
            "--no-deps",
            "--force-recreate",
            "--exit-code-from",
            "temporal-namespace",
            "temporal-namespace",
            timeout=120,
        )

        compose(project, "stop", "redis", timeout=60)
        failed = subprocess.run(
            ["uv", "run", "network-lab-check"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert failed.returncode != 0
        assert "redis" in (failed.stdout + failed.stderr).lower()
        start(project)
        recovered = subprocess.run(
            ["uv", "run", "network-lab-check"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr

        compose(project, "down", "--volumes", "--remove-orphans", timeout=180)
        start(project)
        reset_tag = httpx.get(tag_url, headers=headers, timeout=settings.probe_timeout_seconds)
        assert reset_tag.status_code == 404
        asyncio.run(assert_temporal_namespace(settings, "default"))
        with pytest.raises(RPCError):
            asyncio.run(assert_temporal_namespace(settings, namespace))
        reset_topics = AdminClient(
            {"bootstrap.servers": settings.kafka_bootstrap_servers}
        ).list_topics(timeout=settings.probe_timeout_seconds)
        assert topic not in reset_topics.topics
    finally:
        # The opt-in and project-name assertions above authorize only this project's reset.
        compose(collision_project, "down", "--volumes", "--remove-orphans", timeout=120)
        compose(project, "down", "--volumes", "--remove-orphans", timeout=180)
