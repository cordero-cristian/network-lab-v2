from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from ipaddress import IPv4Address
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from confluent_kafka import Consumer, KafkaError
from temporalio import activity
from temporalio.api.enums.v1 import EventType
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.service import RPCError
from temporalio.worker import Worker

from network_automation.activities.deployment import (
    deploy_device_artifact,
    prepare_device_deployment,
    validate_device_state,
)
from network_automation.activities.rendering import publish_render_result
from network_automation.devices.srlinux import (
    HOSTNAME_PATH,
    SRLinuxClient,
    disable_pygnmi_logging,
    interface_admin_path,
    interface_oper_path,
    ipv4_address_status_path,
    local_asn_path,
    neighbor_peer_as_path,
    neighbor_session_state_path,
    subinterface_admin_path,
    subinterface_oper_path,
)
from network_automation.events.models import (
    DeploymentCompleted,
    DeploymentFailed,
    DeploymentRequested,
    DeploymentResult,
    DeployDeviceConfigRequest,
    DeploymentTarget,
    PreparedDeployment,
    deployment_workflow_id_for,
)
from network_automation.events.producer import publish_event
from network_automation.settings import LabSettings
from network_automation.workflows.render_device import RenderDeviceConfigWorkflow
from tests.integration.support.nautobot_fixture import (
    FixtureApi,
    create_deployment_devices,
)

pytestmark = pytest.mark.integration

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEVICE_NETWORK = "network-lab-devices-mgmt"
DEVICE_IMAGE = "ghcr.io/nokia/srlinux:26.7.2-519"
DEVICE_NODES = {
    "f004-spine01": "172.31.46.11",
    "f004-leaf01": "172.31.46.12",
}
NETLAB_VERSION = "26.8.0"
CONTAINERLAB_VERSION = "0.79.0"
REJECTION_DESCRIPTION_PATH = "/interface[name=system0]/description"


def _run_read_only_command(*command: str) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPOSITORY_ROOT,
        )
    except FileNotFoundError:
        pytest.fail(f"required real-infrastructure command is absent: {command[0]}")
    return result.stdout.strip()


def _assert_tool_version(command: str, expected: str) -> None:
    output = _run_read_only_command(command, "version")
    versions = re.findall(r"(?<![\d.])\d+\.\d+(?:\.\d+)?(?![\d.])", output)
    def normalized(version: str) -> tuple[int, ...]:
        parts = tuple(int(part) for part in version.split("."))
        return parts[:-1] if len(parts) == 3 and parts[-1] == 0 else parts

    normalized_expected = normalized(expected)
    normalized_versions = {
        normalized(version) for version in versions
    }
    assert normalized_expected in normalized_versions, (
        f"expected {command} {expected}, got {output!r}"
    )


def _inspect_containers(*containers: str) -> list[dict[str, Any]]:
    output = _run_read_only_command("docker", "inspect", *containers)
    inspected = json.loads(output)
    assert isinstance(inspected, list)
    return inspected


def _assert_topology_containers() -> None:
    expected_containers = {
        f"clab-feature004-{node}": (node, address)
        for node, address in DEVICE_NODES.items()
    }
    actual_containers = set(
        _run_read_only_command(
            "docker",
            "ps",
            "--all",
            "--filter",
            "label=containerlab=feature004",
            "--format",
            "{{.Names}}",
        ).splitlines()
    )
    assert actual_containers == set(expected_containers)

    for container in _inspect_containers(*sorted(expected_containers)):
        name = str(container["Name"]).removeprefix("/")
        node, address = expected_containers[name]
        config = container["Config"]
        state = container["State"]
        networks = container["NetworkSettings"]["Networks"]
        assert state["Running"] is True, f"{node} is not running"
        assert config["Image"] == DEVICE_IMAGE, f"{node} uses the wrong image"
        assert set(networks) == {DEVICE_NETWORK}
        assert networks[DEVICE_NETWORK]["IPAddress"] == address


def _assert_worker_device_network() -> None:
    worker_id = _run_read_only_command(
        "docker",
        "compose",
        "--file",
        "compose.yaml",
        "--file",
        "compose.device-access.yaml",
        "--profile",
        "automation",
        "ps",
        "--quiet",
        "automation-worker",
    )
    assert worker_id and "\n" not in worker_id, "automation worker is not running"
    worker = _inspect_containers(worker_id)[0]
    assert worker["State"]["Running"] is True
    assert DEVICE_NETWORK in worker["NetworkSettings"]["Networks"]


def _assert_device_gnmi_preflight(settings: LabSettings) -> None:
    assert settings.device_username is not None, "LAB_DEVICE_USERNAME is required"
    assert settings.device_password is not None, "LAB_DEVICE_PASSWORD is required"
    assert settings.device_gnmi_port == 57401, "the canonical gNMI port is required"
    client = SRLinuxClient(
        username=settings.device_username,
        password=settings.device_password.get_secret_value(),
        timeout_seconds=settings.device_gnmi_timeout_seconds,
    )

    for node, address in DEVICE_NODES.items():
        target = DeploymentTarget(
            device_name=node,
            management_address=address,
            platform="nokia_srl",
            gnmi_port=settings.device_gnmi_port,
            tls_mode="insecure",
        )
        with client._client(target) as gnmi:
            disable_pygnmi_logging()
            capabilities = gnmi.capabilities()
            client._require_native_system_model(capabilities)
            hostname = client._get(gnmi, HOSTNAME_PATH, datatype="all")
        assert hostname == node, f"gNMI identity mismatch for {node}"


@pytest.fixture(scope="module", autouse=True)
def real_topology_preflight() -> None:
    _assert_tool_version("netlab", NETLAB_VERSION)
    _assert_tool_version("containerlab", CONTAINERLAB_VERSION)
    _assert_topology_containers()
    _assert_worker_device_network()
    _assert_device_gnmi_preflight(LabSettings())


def test_real_preflight_confirms_both_targets_without_mutation() -> None:
    """The module preflight completes before any fixture or device mutation."""


def _result_consumer(settings: LabSettings) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": f"feature004-results-{uuid4().hex}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "topic.metadata.refresh.interval.ms": 1000,
        }
    )
    consumer.subscribe(
        [settings.deployment_completed_topic, settings.deployment_failed_topic]
    )
    return consumer


def _wait_for_results(
    consumer: Consumer, correlation_ids: set[UUID], *, timeout: float = 180
) -> dict[UUID, DeploymentCompleted | DeploymentFailed]:
    results: dict[UUID, DeploymentCompleted | DeploymentFailed] = {}
    deadline = time.monotonic() + timeout
    while correlation_ids - results.keys() and time.monotonic() < deadline:
        message = consumer.poll(min(2, deadline - time.monotonic()))
        if message is None:
            continue
        error = message.error()
        if error is not None and error.code() in {
            KafkaError.UNKNOWN_TOPIC_OR_PART,
            KafkaError._PARTITION_EOF,
        }:
            continue
        assert error is None
        payload = json.loads(message.value())
        correlation_id = payload.get("correlation_id")
        if correlation_id not in {str(value) for value in correlation_ids}:
            continue
        if payload.get("event_type") == "network.deployment.completed":
            result: DeploymentCompleted | DeploymentFailed = (
                DeploymentCompleted.model_validate(payload)
            )
        elif payload.get("event_type") == "network.deployment.failed":
            result = DeploymentFailed.model_validate(payload)
        else:
            continue
        results[result.correlation_id] = result
    assert results.keys() == correlation_ids, "not all deployment outcomes were received"
    return results


def _matching_result_records(
    consumer: Consumer,
    correlation_id: UUID,
    *,
    timeout: float = 180,
    quiet_period: float = 3,
) -> list[tuple[DeploymentCompleted | DeploymentFailed, bytes]]:
    records: list[tuple[DeploymentCompleted | DeploymentFailed, bytes]] = []
    deadline = time.monotonic() + timeout
    quiet_deadline: float | None = None
    while time.monotonic() < deadline:
        if quiet_deadline is not None and time.monotonic() >= quiet_deadline:
            break
        remaining = (quiet_deadline or deadline) - time.monotonic()
        message = consumer.poll(min(1, max(0, remaining)))
        if message is None:
            continue
        error = message.error()
        if error is not None and error.code() in {
            KafkaError.UNKNOWN_TOPIC_OR_PART,
            KafkaError._PARTITION_EOF,
        }:
            continue
        assert error is None
        raw = message.value()
        payload = json.loads(raw)
        if payload.get("correlation_id") != str(correlation_id):
            continue
        if payload.get("event_type") == "network.deployment.completed":
            result: DeploymentCompleted | DeploymentFailed = (
                DeploymentCompleted.model_validate(payload)
            )
        elif payload.get("event_type") == "network.deployment.failed":
            result = DeploymentFailed.model_validate(payload)
        else:
            continue
        records.append((result, raw))
        quiet_deadline = time.monotonic() + quiet_period
    assert records, f"no deployment outcome received for correlation ID {correlation_id}"
    return records


def _activity_attempts(history: object) -> Counter[str]:
    scheduled = {
        event.event_id: event.activity_task_scheduled_event_attributes.activity_type.name
        for event in history.events  # type: ignore[attr-defined]
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    }
    attempts: Counter[str] = Counter()
    for event in history.events:  # type: ignore[attr-defined]
        if event.event_type != EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED:
            continue
        started = event.activity_task_started_event_attributes
        name = scheduled[started.scheduled_event_id]
        attempts[name] = max(attempts[name], started.attempt)
    return attempts


def _scheduled_activities(history: object) -> list[str]:
    return [
        event.activity_task_scheduled_event_attributes.activity_type.name
        for event in history.events  # type: ignore[attr-defined]
        if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_SCHEDULED
    ]


async def _wait_for_validation_failure(handle: Any, *, timeout: float = 45) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            description = await handle.describe()
        except RPCError:
            await asyncio.sleep(0.5)
            continue
        for pending in description.raw_description.pending_activities:
            if (
                pending.activity_type.name == "validate_device_state"
                and pending.attempt >= 2
            ):
                return
        await asyncio.sleep(0.5)
    pytest.fail("validation did not demonstrate temporary non-convergence")


def _client_for(settings: LabSettings, *, password: str | None = None) -> SRLinuxClient:
    assert settings.device_username is not None, "LAB_DEVICE_USERNAME is required"
    assert settings.device_password is not None, "LAB_DEVICE_PASSWORD is required"
    return SRLinuxClient(
        username=settings.device_username,
        password=password or settings.device_password.get_secret_value(),
        timeout_seconds=settings.device_gnmi_timeout_seconds,
    )


def _apply_cli(client: SRLinuxClient, target: DeploymentTarget, artifact: str) -> None:
    with client._client(target) as gnmi:
        disable_pygnmi_logging()
        gnmi.set(update=[("/cli://", artifact)], encoding="ascii")


def _wait_for_native_state(
    client: SRLinuxClient,
    prepared: PreparedDeployment,
    *,
    timeout: float = 45,
) -> dict[str, str | int | bool | None]:
    expected = _expected_native_state(prepared)
    deadline = time.monotonic() + timeout
    observed: dict[str, str | int | bool | None] = {}
    while time.monotonic() < deadline:
        observed = client.read_native_state(prepared)
        if observed == expected:
            return observed
        time.sleep(1)
    pytest.fail(f"device {prepared.target.device_name} did not reach intended state")


def _assert_no_matching_result(
    consumer: Consumer, correlation_id: UUID, *, timeout: float = 5
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = consumer.poll(min(1, deadline - time.monotonic()))
        if message is None:
            continue
        error = message.error()
        if error is not None and error.code() in {
            KafkaError.UNKNOWN_TOPIC_OR_PART,
            KafkaError._PARTITION_EOF,
        }:
            continue
        assert error is None
        payload = json.loads(message.value())
        assert payload.get("correlation_id") != str(correlation_id), (
            "retained duplicate produced another deployment outcome"
        )


async def _run_isolated_deployment(
    settings: LabSettings,
    prepared: PreparedDeployment,
    *,
    deployment_activity: Any = deploy_device_artifact,
) -> tuple[DeploymentRequested, DeploymentCompleted | DeploymentFailed, object]:
    task_queue = f"feature004-isolated-{uuid4().hex}"
    temporal = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
    event = DeploymentRequested(
        event_type="network.deployment.requested",
        event_version=1,
        event_id=uuid4(),
        correlation_id=uuid4(),
        device_name=prepared.target.device_name,
        requested_at=datetime.now(timezone.utc),
        source="integration-isolated",
    )
    request = DeployDeviceConfigRequest(
        operation="deploy",
        event_id=event.event_id,
        correlation_id=event.correlation_id,
        device_name=event.device_name,
    )

    @activity.defn(name="prepare_device_deployment")
    async def use_test_owned_preparation(_: DeployDeviceConfigRequest) -> PreparedDeployment:
        return prepared

    with ThreadPoolExecutor(max_workers=3) as activity_executor:
        async with Worker(
            temporal,
            task_queue=task_queue,
            workflows=[RenderDeviceConfigWorkflow],
            activities=[
                use_test_owned_preparation,
                deployment_activity,
                validate_device_state,
                publish_render_result,
            ],
            activity_executor=activity_executor,
        ):
            handle = await temporal.start_workflow(
                RenderDeviceConfigWorkflow.run,
                request,
                id=deployment_workflow_id_for(event.event_id),
                task_queue=task_queue,
            )
            result = await asyncio.wait_for(handle.result(), timeout=180)
            history = await handle.fetch_history()
    return event, result, history


def _expected_native_state(
    prepared: PreparedDeployment,
) -> dict[str, str | int]:
    expected = prepared.expected_state
    state: dict[str, str | int] = {HOSTNAME_PATH: expected.device_name}
    interfaces = ((expected.loopback_name, str(expected.loopback_prefix)),) + tuple(
        (interface.name, str(interface.ipv4_prefix))
        for interface in expected.routed_interfaces
    )
    for name, prefix in interfaces:
        state[interface_admin_path(name)] = "enable"
        state[interface_oper_path(name)] = "up"
        state[subinterface_admin_path(name)] = "enable"
        state[subinterface_oper_path(name)] = "up"
        state[ipv4_address_status_path(name, prefix)] = "preferred"
    state[local_asn_path()] = expected.local_asn
    for neighbor in expected.bgp_neighbors:
        address = str(neighbor.address)
        state[neighbor_peer_as_path(address)] = neighbor.remote_asn
        state[neighbor_session_state_path(address)] = "established"
    return state


def test_real_two_node_deployment_reaches_and_reports_intended_state() -> None:
    settings = LabSettings()
    assert settings.device_username is not None, "LAB_DEVICE_USERNAME is required"
    assert settings.device_password is not None, "LAB_DEVICE_PASSWORD is required"

    fixture = FixtureApi(settings)
    marker = f"feature004-{uuid4().hex[:10]}"
    device_names = ("f004-spine01", "f004-leaf01")
    artifact_paths = {
        Path("artifacts/configs") / f"{device_name}.cfg"
        for device_name in device_names
    }
    results = _result_consumer(settings)
    try:
        assert create_deployment_devices(fixture, marker=marker) == device_names
        requests = tuple(
            DeploymentRequested(
                event_type="network.deployment.requested",
                event_version=1,
                event_id=uuid4(),
                correlation_id=uuid4(),
                device_name=device_name,
                requested_at=datetime.now(timezone.utc),
                source="integration",
            )
            for device_name in device_names
        )
        prepared = {
            request.device_name: prepare_device_deployment(
                DeployDeviceConfigRequest(
                    operation="deploy",
                    event_id=request.event_id,
                    correlation_id=request.correlation_id,
                    device_name=request.device_name,
                )
            )
            for request in requests
        }

        for request in requests:
            publish_event(request, settings)
        outcomes = _wait_for_results(
            results, {request.correlation_id for request in requests}
        )

        for request in requests:
            outcome = outcomes[request.correlation_id]
            assert isinstance(outcome, DeploymentCompleted), outcome
            identity = prepared[request.device_name].artifact
            assert outcome.device_name == request.device_name
            assert outcome.artifact_path == identity.artifact_path
            assert outcome.artifact_sha256 == identity.sha256
            assert outcome.artifact_bytes == identity.byte_count
            assert outcome.validation_status == "passed"

        client = SRLinuxClient(
            username=settings.device_username,
            password=settings.device_password.get_secret_value(),
            timeout_seconds=settings.device_gnmi_timeout_seconds,
        )
        for value in prepared.values():
            assert client.read_native_state(value) == _expected_native_state(value)
    finally:
        results.close()
        for path in artifact_paths:
            path.unlink(missing_ok=True)
        try:
            fixture.cleanup()
        finally:
            fixture.close()


@pytest.mark.asyncio
async def test_real_duplicate_lost_response_and_validation_convergence_are_isolated() -> None:
    settings = LabSettings()
    fixture = FixtureApi(settings)
    marker = f"feature004-recovery-{uuid4().hex[:8]}"
    artifact_paths = {
        Path("artifacts/configs/f004-spine01.cfg"),
        Path("artifacts/configs/f004-leaf01.cfg"),
    }
    results = _result_consumer(settings)
    client = _client_for(settings)
    prepared: dict[str, PreparedDeployment] = {}
    restoration_failures: list[str] = []
    try:
        create_deployment_devices(fixture, marker=marker)
        request = DeploymentRequested(
            event_type="network.deployment.requested",
            event_version=1,
            event_id=uuid4(),
            correlation_id=uuid4(),
            device_name="f004-spine01",
            requested_at=datetime.now(timezone.utc),
            source="integration-recovery",
        )
        prepared = {
            name: prepare_device_deployment(
                DeployDeviceConfigRequest(
                    operation="deploy",
                    event_id=uuid4(),
                    correlation_id=uuid4(),
                    device_name=name,
                )
            )
            for name in DEVICE_NODES
        }

        # Establish a known test-owned baseline, then remove only the leaf BGP
        # subtree so the spine workflow must wait for its real peer.
        for value in prepared.values():
            client.deploy(value)
        for value in prepared.values():
            _wait_for_native_state(client, value)
        _apply_cli(
            client,
            prepared["f004-leaf01"].target,
            "delete / network-instance default protocols bgp\n",
        )

        temporal = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            data_converter=pydantic_data_converter,
        )
        publish_event(request, settings)
        publish_event(request, settings)
        workflow_id = deployment_workflow_id_for(request.event_id)
        handle = temporal.get_workflow_handle(workflow_id)
        await _wait_for_validation_failure(handle)

        # Apply successfully, then discard the first activity result so Temporal
        # repeats the same digest-bound declarative Set.
        leaf = prepared["f004-leaf01"]
        lost_response_attempts = 0

        @activity.defn(name="deploy_device_artifact")
        def discard_first_success(value: PreparedDeployment) -> DeploymentResult:
            nonlocal lost_response_attempts
            result = deploy_device_artifact(value)
            lost_response_attempts += 1
            if lost_response_attempts == 1:
                raise ApplicationError(
                    "device gNMI endpoint is unavailable",
                    type="device_unavailable",
                    non_retryable=False,
                )
            return result

        _, recovery_outcome, recovery_history = await _run_isolated_deployment(
            settings,
            leaf,
            deployment_activity=discard_first_success,
        )
        assert isinstance(recovery_outcome, DeploymentCompleted)
        recovery_attempts = _activity_attempts(recovery_history)
        assert recovery_attempts["prepare_device_deployment"] == 1
        assert recovery_attempts["deploy_device_artifact"] == 2
        assert recovery_attempts["validate_device_state"] >= 1
        assert recovery_attempts["publish_render_result"] == 1
        assert lost_response_attempts == 2
        assert _wait_for_native_state(client, leaf) == _expected_native_state(leaf)

        outcome = DeploymentCompleted.model_validate(
            await asyncio.wait_for(handle.result(), timeout=180)
        )
        history = await handle.fetch_history()
        assert outcome.workflow_id == workflow_id
        assert _scheduled_activities(history) == [
            "prepare_device_deployment",
            "deploy_device_artifact",
            "validate_device_state",
            "publish_render_result",
        ]
        attempts = _activity_attempts(history)
        assert attempts["prepare_device_deployment"] == 1
        assert attempts["deploy_device_artifact"] == 1
        assert attempts["validate_device_state"] >= 2
        assert attempts["publish_render_result"] == 1

        records = await asyncio.to_thread(
            _matching_result_records, results, request.correlation_id
        )
        assert len(records) == 1
        assert records[0][0] == outcome

        description = await handle.describe()
        retained_run_id = (
            description.raw_description.workflow_execution_info.execution.run_id
        )
        publish_event(request, settings)
        await asyncio.to_thread(
            _assert_no_matching_result, results, request.correlation_id
        )
        duplicate_input = DeployDeviceConfigRequest(
            operation="deploy",
            event_id=request.event_id,
            correlation_id=request.correlation_id,
            device_name=request.device_name,
        )
        with pytest.raises(WorkflowAlreadyStartedError):
            await temporal.start_workflow(
                RenderDeviceConfigWorkflow.run,
                duplicate_input,
                id=workflow_id,
                task_queue=settings.temporal_task_queue,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
            )
        retained = await handle.describe()
        assert (
            retained.raw_description.workflow_execution_info.execution.run_id
            == retained_run_id
        )
    finally:
        # Restore only the exact Feature 004 declarations changed by this test.
        for value in prepared.values():
            try:
                client.deploy(value)
            except Exception as exc:
                restoration_failures.append(
                    f"{value.target.device_name}: {type(exc).__name__}"
                )
        results.close()
        for path in artifact_paths:
            path.unlink(missing_ok=True)
        try:
            fixture.cleanup()
        finally:
            fixture.close()
        assert not restoration_failures, (
            f"device restoration failures: {restoration_failures}"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "failure_stage", "error_type", "deploy_attempts", "validate_attempts"),
    (
        ("unreachable", "deploy", "device_unavailable", 3, 0),
        ("bad-credentials", "deploy", "device_authentication_failed", 1, 0),
        ("atomic-rejection", "deploy", "configuration_rejected", 1, 0),
        ("validation-mismatch", "validate", "validation_failed", 1, 1),
    ),
)
async def test_real_failure_outcomes_are_safe_bounded_and_restore_owned_state(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    case: str,
    failure_stage: str,
    error_type: str,
    deploy_attempts: int,
    validate_attempts: int,
) -> None:
    caplog.set_level(logging.INFO)
    settings = LabSettings()
    fixture = FixtureApi(settings)
    marker = f"feature004-failure-{uuid4().hex[:8]}"
    artifact_paths = {
        Path("artifacts/configs/f004-spine01.cfg"),
        Path("artifacts/configs/f004-leaf01.cfg"),
    }
    results = _result_consumer(settings)
    client = _client_for(settings)
    prepared: PreparedDeployment | None = None
    baseline: dict[str, str | int | bool | None] | None = None
    original_artifact: bytes | None = None
    rejected_marker = f"f004-rejected-{uuid4().hex}"
    secret = f"f004-secret-{uuid4().hex}"
    description_before: object = None
    restoration_failures: list[str] = []
    try:
        create_deployment_devices(fixture, marker=marker)
        prepared_by_name = {
            name: prepare_device_deployment(
                DeployDeviceConfigRequest(
                    operation="deploy",
                    event_id=uuid4(),
                    correlation_id=uuid4(),
                    device_name=name,
                )
            )
            for name in DEVICE_NODES
        }
        for value in prepared_by_name.values():
            client.deploy(value)
        for value in prepared_by_name.values():
            _wait_for_native_state(client, value)
        prepared = prepared_by_name["f004-leaf01"]
        baseline = client.read_native_state(prepared)
        artifact_path = Path(prepared.artifact.artifact_path)
        original_artifact = artifact_path.read_bytes()

        case_prepared = prepared
        if case == "unreachable":
            assert "172.31.46.250" not in _run_read_only_command(
                "docker", "network", "inspect", DEVICE_NETWORK
            )
            case_prepared = prepared.model_copy(
                update={
                    "target": prepared.target.model_copy(
                        update={"management_address": IPv4Address("172.31.46.250")}
                    )
                }
            )
        elif case == "bad-credentials":
            monkeypatch.setenv("LAB_DEVICE_PASSWORD", secret)
        elif case == "atomic-rejection":
            with client._client(prepared.target) as gnmi:
                description_before = client._get(
                    gnmi, REJECTION_DESCRIPTION_PATH, datatype="all"
                )
            rejected = (
                f"set / interface system0 description {rejected_marker}\n"
                "set / feature004-invalid-path value\n"
            ).encode("ascii")
            artifact_path.write_bytes(rejected)
            case_prepared = prepared.model_copy(
                update={
                    "artifact": prepared.artifact.model_copy(
                        update={
                            "sha256": hashlib.sha256(rejected).hexdigest(),
                            "byte_count": len(rejected),
                        }
                    )
                }
            )
        elif case == "validation-mismatch":
            case_prepared = prepared.model_copy(
                update={
                    "expected_state": prepared.expected_state.model_copy(
                        update={"local_asn": prepared.expected_state.local_asn + 1}
                    )
                }
            )

        event, workflow_result, history = await _run_isolated_deployment(
            settings, case_prepared
        )
        records = await asyncio.to_thread(
            _matching_result_records, results, event.correlation_id
        )
        assert len(records) == 1
        outcome, raw_event = records[0]
        assert workflow_result == outcome
        assert isinstance(outcome, DeploymentFailed), outcome
        assert outcome.failure_stage == failure_stage
        assert outcome.error_type == error_type
        assert len(outcome.error_message) <= 256
        assert outcome.workflow_id == deployment_workflow_id_for(event.event_id)
        assert set(json.loads(raw_event)) == {
            "event_type",
            "event_version",
            "event_id",
            "correlation_id",
            "device_name",
            "workflow_id",
            "failure_stage",
            "error_type",
            "error_message",
            "failed_at",
            "artifact_sha256",
            "artifact_bytes",
            "deployed_at",
        }
        attempts = _activity_attempts(history)
        assert attempts["prepare_device_deployment"] == 1
        assert attempts["deploy_device_artifact"] == deploy_attempts
        assert attempts["validate_device_state"] == validate_attempts
        assert attempts["publish_render_result"] == 1
        assert _scheduled_activities(history) == [
            "prepare_device_deployment",
            "deploy_device_artifact",
            *(["validate_device_state"] if validate_attempts else []),
            "publish_render_result",
        ]
        for forbidden in (secret, rejected_marker, "feature004-invalid-path", "set / "):
            assert forbidden.encode() not in raw_event
            assert forbidden not in str(history)
            assert forbidden not in caplog.text
        for forbidden in (
            "password",
            "credential",
            "management_address",
            "raw_response",
            "traceback",
            "stack",
        ):
            assert forbidden.encode() not in raw_event
        for forbidden in ("raw_response", "traceback", "stack"):
            assert forbidden not in caplog.text.lower()

        if case == "bad-credentials":
            original_password = settings.device_password
            assert original_password is not None
            monkeypatch.setenv(
                "LAB_DEVICE_PASSWORD", original_password.get_secret_value()
            )
        if case == "atomic-rejection":
            with client._client(prepared.target) as gnmi:
                description_after = client._get(
                    gnmi, REJECTION_DESCRIPTION_PATH, datatype="all"
                )
            assert description_after == description_before
            assert description_after != rejected_marker
        assert client.read_native_state(prepared) == baseline
    finally:
        if prepared is not None and original_artifact is not None:
            Path(prepared.artifact.artifact_path).write_bytes(original_artifact)
            try:
                client.deploy(prepared)
            except Exception as exc:
                restoration_failures.append(
                    f"{prepared.target.device_name}: {type(exc).__name__}"
                )
        results.close()
        for path in artifact_paths:
            path.unlink(missing_ok=True)
        try:
            fixture.cleanup()
        finally:
            fixture.close()
        assert not restoration_failures, (
            f"device restoration failures: {restoration_failures}"
        )
