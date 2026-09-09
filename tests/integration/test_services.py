from __future__ import annotations

import asyncio
import subprocess
import uuid

import httpx
import pytest
from confluent_kafka import Consumer, Producer
from confluent_kafka.admin import AdminClient
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest
from temporalio.client import Client

from network_automation.health import run_checks
from network_automation.settings import LabSettings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def settings() -> LabSettings:
    return LabSettings()


def test_aggregate_application_readiness(settings: LabSettings) -> None:
    results = asyncio.run(run_checks(settings))
    failures = [f"{result.name}: {result.detail}" for result in results if not result.ok]
    assert not failures, "; ".join(failures)


def test_authenticated_nautobot_api(settings: LabSettings) -> None:
    response = httpx.get(
        f"{str(settings.nautobot_url).rstrip('/')}/api/status/",
        headers={"Authorization": f"Token {settings.nautobot_token.get_secret_value()}"},
        timeout=settings.probe_timeout_seconds,
    )
    response.raise_for_status()
    assert response.json()["nautobot-version"].startswith("2.4.")


def test_kafka_host_round_trip_and_advertised_metadata(settings: LabSettings) -> None:
    topic = f"network-lab-smoke-{uuid.uuid4().hex}"
    payload = uuid.uuid4().hex.encode()
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    metadata = admin.list_topics(timeout=settings.probe_timeout_seconds)
    expected_port = settings.kafka_host_port
    assert any(
        broker.host in {"localhost", "127.0.0.1"} and broker.port == expected_port
        for broker in metadata.brokers.values()
    )
    try:
        producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
        producer.produce(topic, payload)
        assert producer.flush(settings.probe_timeout_seconds) == 0

        consumer = Consumer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "group.id": f"smoke-{uuid.uuid4().hex}",
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
    finally:
        admin.delete_topics([topic])[topic].result(settings.probe_timeout_seconds)


def test_kafka_internal_listener(settings: LabSettings) -> None:
    topic = f"network-lab-internal-{uuid.uuid4().hex}"
    base = [
        "docker", "compose", "--project-name", settings.compose_project,
        "exec", "-T", "kafka",
    ]
    metadata = subprocess.run(
        [*base, "/opt/kafka/bin/kafka-broker-api-versions.sh", "--bootstrap-server", "kafka:29092"],
        check=True, capture_output=True, text=True, timeout=settings.probe_timeout_seconds,
    )
    assert "kafka:29092" in metadata.stdout
    try:
        subprocess.run(
            [
                *base, "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "kafka:29092",
                "--create", "--topic", topic, "--partitions", "1", "--replication-factor", "1",
            ],
            check=True, capture_output=True, text=True, timeout=settings.probe_timeout_seconds,
        )
        subprocess.run(
            [
                *base, "/opt/kafka/bin/kafka-console-producer.sh",
                "--bootstrap-server", "kafka:29092", "--topic", topic,
            ],
            input="internal-round-trip\n", check=True, capture_output=True, text=True,
            timeout=settings.probe_timeout_seconds,
        )
        consumed = subprocess.run(
            [
                *base, "/opt/kafka/bin/kafka-console-consumer.sh",
                "--bootstrap-server", "kafka:29092", "--topic", topic,
                "--from-beginning", "--max-messages", "1", "--timeout-ms", "10000",
            ],
            check=True, capture_output=True, text=True,
            timeout=settings.probe_timeout_seconds + 5,
        )
        assert consumed.stdout.strip() == "internal-round-trip"
    finally:
        subprocess.run(
            [
                *base, "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "kafka:29092",
                "--delete", "--topic", topic,
            ],
            check=False, capture_output=True, text=True, timeout=settings.probe_timeout_seconds,
        )


async def test_temporal_rpc_namespace_and_ui(settings: LabSettings) -> None:
    client = await asyncio.wait_for(
        Client.connect(settings.temporal_address, namespace=settings.temporal_namespace),
        timeout=settings.probe_timeout_seconds,
    )
    assert await asyncio.wait_for(
        client.service_client.check_health(), timeout=settings.probe_timeout_seconds
    )
    described = await asyncio.wait_for(
        client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=settings.temporal_namespace)
        ),
        timeout=settings.probe_timeout_seconds,
    )
    assert described.namespace_info.name == settings.temporal_namespace
    response = httpx.get(
        f"{str(settings.temporal_ui_url).rstrip('/')}/api/v1/namespaces",
        timeout=settings.probe_timeout_seconds,
    )
    response.raise_for_status()
    names = {item["namespaceInfo"]["name"] for item in response.json()["namespaces"]}
    assert settings.temporal_namespace in names
