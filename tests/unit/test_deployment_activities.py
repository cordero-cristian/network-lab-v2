from __future__ import annotations

from collections.abc import Iterator
import hashlib
import logging
from datetime import timezone
from ipaddress import IPv4Address
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import httpx
import pytest
from temporalio.exceptions import ApplicationError

from network_automation.activities import deployment
from network_automation.devices import srlinux
from network_automation.devices.srlinux import (
    ArtifactMismatchError,
    DeviceAuthenticationError,
    DeviceConfigurationError,
    DeviceConnectionError,
    DeviceIdentityError,
    DevicePathError,
    DevicePlatformError,
    DeviceResponseError,
    HOSTNAME_PATH,
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
    ArtifactIdentity,
    DeploymentTarget,
    DeployDeviceConfigRequest,
    ExpectedBgpNeighbor,
    ExpectedDeviceState,
    ExpectedInterface,
    PreparedDeployment,
)
from network_automation.intent.models import (
    BgpIntent,
    BgpNeighborIntent,
    DeviceIntent,
    InterfaceIntent,
    LoopbackIntent,
)
from network_automation.intent.nautobot import NautobotDeploymentIntent, NautobotError
from network_automation.rendering.srlinux import (
    _ArtifactWriteResult,
    _write_srlinux_artifact,
)


EVENT_ID = UUID("08660568-3d4c-4901-9a77-8a4fb0e68072")
CORRELATION_ID = UUID("eaf41a9d-9cb8-4de0-bd68-32bbc47e5030")
DEVICE_NAME = "f004-leaf01"
MANAGEMENT_ADDRESS = IPv4Address("172.31.46.12")


def request() -> DeployDeviceConfigRequest:
    return DeployDeviceConfigRequest(
        operation="deploy",
        event_id=EVENT_ID,
        correlation_id=CORRELATION_ID,
        device_name=DEVICE_NAME,
    )


def intent() -> DeviceIntent:
    return DeviceIntent(
        name=DEVICE_NAME,
        platform="nokia_srl",
        platform_display="Nokia SR Linux",
        role="leaf",
        location="feature004",
        loopback=LoopbackIntent(description="router id", ipv4="10.0.0.2/32"),
        interfaces=(
            InterfaceIntent(
                name="ethernet-1/1",
                description="to f004-spine01",
                ipv4="192.0.2.1/31",
            ),
        ),
        bgp=BgpIntent(
            local_asn=65001,
            neighbors=(
                BgpNeighborIntent(
                    address="192.0.2.0",
                    remote_asn=65000,
                    description="f004-spine01",
                ),
            ),
        ),
    )


def prepared(*, require_oper_up: bool = True) -> PreparedDeployment:
    return PreparedDeployment(
        artifact=ArtifactIdentity(
            device_name=DEVICE_NAME,
            artifact_path=f"artifacts/configs/{DEVICE_NAME}.cfg",
            sha256="cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887",
            byte_count=1248,
        ),
        target=DeploymentTarget(
            device_name=DEVICE_NAME,
            management_address=MANAGEMENT_ADDRESS,
            platform="nokia_srl",
            gnmi_port=57401,
            tls_mode="insecure",
        ),
        expected_state=ExpectedDeviceState(
            device_name=DEVICE_NAME,
            loopback_name="system0",
            loopback_prefix="10.0.0.2/32",
            routed_interfaces=(
                ExpectedInterface(
                    name="ethernet-1/1",
                    ipv4_prefix="192.0.2.1/31",
                    require_oper_up=require_oper_up,
                ),
            ),
            local_asn=65001,
            bgp_neighbors=(
                ExpectedBgpNeighbor(address="192.0.2.0", remote_asn=65000),
            ),
        ),
    )


def configure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAUTOBOT_SUPERUSER_PASSWORD", "nautobot-password")
    monkeypatch.setenv("NAUTOBOT_SUPERUSER_API_TOKEN", "nautobot-token")
    monkeypatch.setenv("LAB_DEVICE_USERNAME", "admin")
    monkeypatch.setenv("LAB_DEVICE_PASSWORD", "device-password")
    monkeypatch.setenv("LAB_DEVICE_GNMI_PORT", "57401")
    monkeypatch.setenv("LAB_DEVICE_GNMI_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("LAB_DEVICE_GNMI_TLS_MODE", "insecure")


def assert_application_error(
    raised: pytest.ExceptionInfo[ApplicationError],
    expected_type: str,
    *,
    non_retryable: bool,
) -> None:
    error = raised.value
    assert error.type == expected_type
    assert error.non_retryable is non_retryable
    assert error.message
    assert "super-secret" not in error.message


@pytest.fixture(autouse=True)
def restore_temporal_activity_logger() -> Iterator[None]:
    logger = logging.getLogger("temporalio.activity")
    original = (logger.disabled, logger.propagate, logger.level, tuple(logger.filters))
    yield
    logger.disabled, logger.propagate, logger.level = original[:3]
    logger.filters[:] = original[3]


def install_failing_prepare_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    snapshot: NautobotDeploymentIntent | None = None,
    nautobot_error: Exception | None = None,
    artifact_bytes: bytes | None = None,
    artifact_path: Path | None = None,
    artifact_error: Exception | None = None,
) -> tuple[MagicMock, MagicMock]:
    device_client = MagicMock(name="SRLinuxClient")
    gnmi_client = MagicMock(name="gNMIclient")
    monkeypatch.setattr(deployment, "SRLinuxClient", device_client)
    monkeypatch.setattr(srlinux, "gNMIclient", gnmi_client)

    class FakeNautobotClient:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> FakeNautobotClient:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get_deployment_intent(self, device_name: str) -> NautobotDeploymentIntent:
            assert device_name == DEVICE_NAME
            if nautobot_error is not None:
                raise nautobot_error
            assert snapshot is not None
            return snapshot

    monkeypatch.setattr(deployment, "NautobotClient", FakeNautobotClient)

    if artifact_bytes is not None or artifact_error is not None:
        def write_artifact(
            value: DeviceIntent, output_dir: Path
        ) -> _ArtifactWriteResult:
            assert value.name == DEVICE_NAME
            assert output_dir == Path("artifacts/configs")
            if artifact_error is not None:
                raise artifact_error
            assert artifact_bytes is not None
            path = artifact_path or output_dir / f"{DEVICE_NAME}.cfg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(artifact_bytes)
            return _ArtifactWriteResult(
                path=path,
                sha256=hashlib.sha256(artifact_bytes).hexdigest(),
                byte_count=len(artifact_bytes),
            )

        monkeypatch.setattr(deployment, "_write_srlinux_artifact", write_artifact)

    return device_client, gnmi_client


@pytest.mark.parametrize(
    ("artifact_bytes", "artifact_path", "expected_type"),
    (
        (
            f"set / system name host-name {DEVICE_NAME}\nshow / system\n".encode(),
            None,
            "artifact_invalid",
        ),
        (
            (
                f"set / system name host-name {DEVICE_NAME}\n".encode()
                + b"set / x\n" * (deployment.MAX_ARTIFACT_BYTES // 8 + 1)
            ),
            None,
            "artifact_invalid",
        ),
        (
            f"set / system name host-name {DEVICE_NAME}\n# caf\xe9\n".encode("latin-1"),
            None,
            "artifact_invalid",
        ),
        (b"set / system name host-name another-device\n", None, "artifact_mismatch"),
        (
            f"set / system name host-name {DEVICE_NAME}\n".encode(),
            Path("artifacts/configs/another-device.cfg"),
            "artifact_mismatch",
        ),
    ),
    ids=("malformed", "oversize", "non-ascii", "wrong-hostname", "wrong-path"),
)
def test_prepare_rejects_invalid_or_target_mismatched_artifact_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    artifact_bytes: bytes,
    artifact_path: Path | None,
    expected_type: str,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.chdir(tmp_path)
    snapshot = NautobotDeploymentIntent(
        intent=intent(), management_address=MANAGEMENT_ADDRESS
    )
    device_client, gnmi_client = install_failing_prepare_boundaries(
        monkeypatch,
        snapshot=snapshot,
        artifact_bytes=artifact_bytes,
        artifact_path=artifact_path,
    )

    with pytest.raises(ApplicationError) as raised:
        deployment.prepare_device_deployment(request())

    assert_application_error(raised, expected_type, non_retryable=True)
    device_client.assert_not_called()
    gnmi_client.assert_not_called()


def test_prepare_classifies_bad_primary_ip_as_permanent_before_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    error = NautobotError("primary_ip4 address must be IPv4 interface text")
    error.__cause__ = ValueError("super-secret-invalid-ip")
    device_client, gnmi_client = install_failing_prepare_boundaries(
        monkeypatch, nautobot_error=error
    )

    with pytest.raises(ApplicationError) as raised:
        deployment.prepare_device_deployment(request())

    assert_application_error(
        raised, "management_address_invalid", non_retryable=True
    )
    device_client.assert_not_called()
    gnmi_client.assert_not_called()


def test_prepare_classifies_unsupported_platform_as_permanent_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.chdir(tmp_path)
    unsupported = intent().model_copy(update={"platform": "cisco_ios"})
    snapshot = NautobotDeploymentIntent(
        intent=unsupported, management_address=MANAGEMENT_ADDRESS
    )
    device_client, gnmi_client = install_failing_prepare_boundaries(
        monkeypatch, snapshot=snapshot
    )

    with pytest.raises(ApplicationError) as raised:
        deployment.prepare_device_deployment(request())

    assert_application_error(raised, "unsupported_platform", non_retryable=True)
    device_client.assert_not_called()
    gnmi_client.assert_not_called()


@pytest.mark.parametrize("missing_setting", ("LAB_DEVICE_USERNAME", "LAB_DEVICE_PASSWORD"))
def test_prepare_classifies_missing_device_settings_as_permanent_before_mutation(
    monkeypatch: pytest.MonkeyPatch, missing_setting: str
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.delenv(missing_setting)
    nautobot_client = MagicMock(name="NautobotClient")
    device_client = MagicMock(name="SRLinuxClient")
    gnmi_client = MagicMock(name="gNMIclient")
    monkeypatch.setattr(deployment, "NautobotClient", nautobot_client)
    monkeypatch.setattr(deployment, "SRLinuxClient", device_client)
    monkeypatch.setattr(srlinux, "gNMIclient", gnmi_client)

    with pytest.raises(ApplicationError) as raised:
        deployment.prepare_device_deployment(request())

    assert_application_error(raised, "device_settings_missing", non_retryable=True)
    assert logging.getLogger("temporalio.activity").filters
    nautobot_client.assert_not_called()
    device_client.assert_not_called()
    gnmi_client.assert_not_called()


def test_prepare_classifies_transient_nautobot_failure_as_retryable_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    http_request = httpx.Request("GET", "http://nautobot.test/api/dcim/devices/")
    error = NautobotError("safe Nautobot boundary failure")
    error.__cause__ = httpx.ReadTimeout(
        "authorization=super-secret", request=http_request
    )
    device_client, gnmi_client = install_failing_prepare_boundaries(
        monkeypatch, nautobot_error=error
    )

    with pytest.raises(ApplicationError) as raised:
        deployment.prepare_device_deployment(request())

    assert_application_error(raised, "nautobot_unavailable", non_retryable=False)
    device_client.assert_not_called()
    gnmi_client.assert_not_called()


def test_prepare_classifies_transient_artifact_io_as_retryable_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    snapshot = NautobotDeploymentIntent(
        intent=intent(), management_address=MANAGEMENT_ADDRESS
    )
    device_client, gnmi_client = install_failing_prepare_boundaries(
        monkeypatch,
        snapshot=snapshot,
        artifact_error=OSError("artifact super-secret storage failure"),
    )

    with pytest.raises(ApplicationError) as raised:
        deployment.prepare_device_deployment(request())

    assert_application_error(raised, "artifact_unavailable", non_retryable=False)
    device_client.assert_not_called()
    gnmi_client.assert_not_called()


def test_prepare_uses_one_snapshot_and_reuses_the_sole_renderer_atomic_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.chdir(tmp_path)
    snapshot = NautobotDeploymentIntent(
        intent=intent(), management_address=MANAGEMENT_ADDRESS
    )
    nautobot_reads: list[str] = []
    writes: list[tuple[DeviceIntent, Path, _ArtifactWriteResult, bytes]] = []

    class FakeNautobotClient:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> FakeNautobotClient:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get_deployment_intent(self, device_name: str) -> NautobotDeploymentIntent:
            nautobot_reads.append(device_name)
            return snapshot

    def write_once(value: DeviceIntent, output_dir: Path) -> _ArtifactWriteResult:
        result = _write_srlinux_artifact(value, output_dir)
        writes.append((value, output_dir, result, result.path.read_bytes()))
        return result

    monkeypatch.setattr(deployment, "NautobotClient", FakeNautobotClient)
    monkeypatch.setattr(deployment, "_write_srlinux_artifact", write_once)

    result = deployment.prepare_device_deployment(request())

    assert nautobot_reads == [DEVICE_NAME]
    assert len(writes) == 1
    written_intent, output_dir, write_result, artifact_bytes = writes[0]
    assert written_intent is snapshot.intent
    assert output_dir == Path("artifacts/configs")
    assert write_result.path == Path(f"artifacts/configs/{DEVICE_NAME}.cfg")
    assert write_result.sha256 == hashlib.sha256(artifact_bytes).hexdigest()
    assert write_result.byte_count == len(artifact_bytes)
    assert result.artifact == ArtifactIdentity(
        device_name=DEVICE_NAME,
        artifact_path=write_result.path.as_posix(),
        sha256=write_result.sha256,
        byte_count=write_result.byte_count,
    )


def test_prepare_binds_supported_artifact_target_expected_checks_and_safe_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.chdir(tmp_path)
    snapshot = NautobotDeploymentIntent(
        intent=intent(), management_address=MANAGEMENT_ADDRESS
    )

    class FakeNautobotClient:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> FakeNautobotClient:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get_deployment_intent(self, device_name: str) -> NautobotDeploymentIntent:
            assert device_name == DEVICE_NAME
            return snapshot

    monkeypatch.setattr(deployment, "NautobotClient", FakeNautobotClient)

    with caplog.at_level(logging.INFO):
        result = deployment.prepare_device_deployment(request())
    artifact_bytes = Path(result.artifact.artifact_path).read_bytes()
    artifact_text = artifact_bytes.decode("ascii")

    assert result.target == DeploymentTarget(
        device_name=DEVICE_NAME,
        management_address=MANAGEMENT_ADDRESS,
        platform="nokia_srl",
        gnmi_port=57401,
        tls_mode="insecure",
    )
    assert result.expected_state == ExpectedDeviceState(
        device_name=DEVICE_NAME,
        loopback_name="system0",
        loopback_prefix="10.0.0.2/32",
        routed_interfaces=(
            ExpectedInterface(
                name="ethernet-1/1",
                ipv4_prefix="192.0.2.1/31",
                require_oper_up=True,
            ),
        ),
        local_asn=65001,
        bgp_neighbors=(
            ExpectedBgpNeighbor(address="192.0.2.0", remote_asn=65000),
        ),
    )
    assert result.artifact.artifact_path == f"artifacts/configs/{DEVICE_NAME}.cfg"
    assert 1 <= result.artifact.byte_count <= 1024 * 1024
    assert result.artifact.byte_count == len(artifact_bytes)
    assert result.artifact.sha256 == hashlib.sha256(artifact_bytes).hexdigest()
    assert artifact_text.endswith("\n")
    assert artifact_text.splitlines()
    assert all(line.startswith("set / ") for line in artifact_text.splitlines())
    hostname_line = f"set / system name host-name {DEVICE_NAME}"
    assert artifact_text.splitlines().count(hostname_line) == 1

    payload = result.model_dump(mode="json")
    serialized = result.model_dump_json()
    assert set(payload) == {"artifact", "target", "expected_state"}
    assert set(payload["artifact"]) == {
        "device_name",
        "artifact_path",
        "sha256",
        "byte_count",
    }
    assert set(payload["target"]) == {
        "device_name",
        "management_address",
        "platform",
        "gnmi_port",
        "tls_mode",
    }
    assert "artifact_content" not in serialized
    assert artifact_text not in serialized
    assert "nautobot-password" not in serialized
    assert "nautobot-token" not in serialized
    assert "device-password" not in serialized
    record = caplog.records[-1]
    assert record.event_type == "network.deployment.requested"  # type: ignore[attr-defined]
    assert record.event_id == str(EVENT_ID)  # type: ignore[attr-defined]
    assert record.correlation_id == str(CORRELATION_ID)  # type: ignore[attr-defined]
    assert record.workflow_id == f"deploy-device-config:{EVENT_ID}"  # type: ignore[attr-defined]
    assert record.device_name == DEVICE_NAME  # type: ignore[attr-defined]
    assert record.activity == "prepare_device_deployment"  # type: ignore[attr-defined]
    assert record.target == str(MANAGEMENT_ADDRESS)  # type: ignore[attr-defined]
    assert artifact_text not in caplog.text
    assert "password" not in caplog.text.lower()
    assert "traceback" not in caplog.text.lower()


def test_deploy_retry_after_artifact_replacement_makes_zero_second_mutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.chdir(tmp_path)
    artifact_text = f"set / system name host-name {DEVICE_NAME}\n"
    artifact_bytes = artifact_text.encode("ascii")
    artifact_path = Path(f"artifacts/configs/{DEVICE_NAME}.cfg")
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(artifact_bytes)
    deployment_input = prepared().model_copy(
        update={
            "artifact": ArtifactIdentity(
                device_name=DEVICE_NAME,
                artifact_path=artifact_path.as_posix(),
                sha256=hashlib.sha256(artifact_bytes).hexdigest(),
                byte_count=len(artifact_bytes),
            )
        }
    )
    gnmi = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value = gnmi
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(srlinux, "gNMIclient", factory)
    gnmi.capabilities.return_value = {
        "supported_models": [{"name": "srl_nokia-system"}]
    }
    gnmi.get.return_value = {
        "notification": [
            {"update": [{"path": HOSTNAME_PATH, "val": DEVICE_NAME}]}
        ]
    }
    gnmi.set.return_value = {"response": [{"op": "UPDATE"}]}

    deployment.deploy_device_artifact(deployment_input)
    artifact_path.write_text(
        f"set / system name host-name {DEVICE_NAME}\n"
        "set / interface ethernet-1/1 admin-state disable\n",
        encoding="ascii",
    )

    with pytest.raises(ApplicationError) as raised:
        deployment.deploy_device_artifact(deployment_input)

    assert_application_error(raised, "artifact_mismatch", non_retryable=True)
    assert factory.call_count == 1
    gnmi.set.assert_called_once_with(
        update=[("/cli://", artifact_text)], encoding="ascii"
    )


@pytest.mark.parametrize(
    ("error", "expected_type", "non_retryable"),
    (
        (DeviceConnectionError("safe"), "device_unavailable", False),
        (
            DeviceAuthenticationError("safe"),
            "device_authentication_failed",
            True,
        ),
        (DeviceIdentityError("safe"), "device_identity_mismatch", True),
        (DevicePlatformError("safe"), "device_platform_mismatch", True),
        (DeviceConfigurationError("safe"), "configuration_rejected", True),
        (ArtifactMismatchError("safe"), "artifact_mismatch", True),
    ),
)
def test_deploy_classifies_safe_device_boundary_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_type: str,
    non_retryable: bool,
) -> None:
    configure_settings(monkeypatch)
    client = MagicMock()
    client.deploy.side_effect = error
    monkeypatch.setattr(deployment, "_client", lambda *_: client)

    with pytest.raises(ApplicationError) as raised:
        deployment.deploy_device_artifact(prepared())

    assert_application_error(
        raised, expected_type, non_retryable=non_retryable
    )


def test_deploy_failure_log_has_safe_workflow_activity_target_and_category_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.setattr(
        deployment.activity,
        "info",
        lambda: SimpleNamespace(workflow_id=f"deploy-device-config:{EVENT_ID}"),
    )
    client = MagicMock()
    client.deploy.side_effect = DeviceConfigurationError(
        "credential=device-password raw_response=set / unsafe traceback stack"
    )
    monkeypatch.setattr(deployment, "_client", lambda *_: client)

    with caplog.at_level(logging.WARNING), pytest.raises(ApplicationError):
        deployment.deploy_device_artifact(prepared())

    record = caplog.records[-1]
    assert record.workflow_id == f"deploy-device-config:{EVENT_ID}"  # type: ignore[attr-defined]
    assert record.device_name == DEVICE_NAME  # type: ignore[attr-defined]
    assert record.activity == "deploy_device_artifact"  # type: ignore[attr-defined]
    assert record.target == str(MANAGEMENT_ADDRESS)  # type: ignore[attr-defined]
    assert record.category == "configuration_rejected"  # type: ignore[attr-defined]
    for forbidden in ("device-password", "raw_response", "set / ", "traceback", "stack"):
        assert forbidden not in caplog.text.lower()


EXPECTED_OBSERVATIONS: dict[str, str | int] = {
    HOSTNAME_PATH: DEVICE_NAME,
    interface_admin_path("system0"): "enable",
    interface_oper_path("system0"): "up",
    subinterface_admin_path("system0"): "enable",
    subinterface_oper_path("system0"): "up",
    ipv4_address_status_path("system0", "10.0.0.2/32"): "preferred",
    interface_admin_path("ethernet-1/1"): "enable",
    interface_oper_path("ethernet-1/1"): "up",
    subinterface_admin_path("ethernet-1/1"): "enable",
    subinterface_oper_path("ethernet-1/1"): "up",
    ipv4_address_status_path("ethernet-1/1", "192.0.2.1/31"): "preferred",
    local_asn_path(): 65001,
    neighbor_peer_as_path("192.0.2.0"): 65000,
    neighbor_session_state_path("192.0.2.0"): "established",
}

EXPECTED_CHECKS: tuple[tuple[str, str | int], ...] = (
    ("system.hostname", DEVICE_NAME),
    ("interface.system0.admin_state", "enable"),
    ("interface.system0.oper_state", "up"),
    ("subinterface.system0.0.admin_state", "enable"),
    ("subinterface.system0.0.oper_state", "up"),
    ("address.system0.10.0.0.2/32.status", "preferred"),
    ("interface.ethernet-1/1.admin_state", "enable"),
    ("interface.ethernet-1/1.oper_state", "up"),
    ("subinterface.ethernet-1/1.0.admin_state", "enable"),
    ("subinterface.ethernet-1/1.0.oper_state", "up"),
    ("address.ethernet-1/1.192.0.2.1/31.status", "preferred"),
    ("routing.bgp.local_asn", 65001),
    ("routing.bgp.neighbor.192.0.2.0.peer_as", 65000),
    ("routing.bgp.neighbor.192.0.2.0.session_state", "established"),
)


def install_device_boundary(
    monkeypatch: pytest.MonkeyPatch, observations: dict[str, str | int | bool | None]
) -> list[str]:
    reads: list[str] = []

    class FakeSRLinuxClient:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def read_native_state(
            self, value: PreparedDeployment
        ) -> dict[str, str | int | bool | None]:
            expected_paths = list(observations)
            reads.extend(expected_paths)
            assert value.target.device_name == DEVICE_NAME
            return observations

    monkeypatch.setattr(deployment, "SRLinuxClient", FakeSRLinuxClient)
    return reads


def test_validation_aggregates_every_exact_invariant_as_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    reads = install_device_boundary(monkeypatch, dict(EXPECTED_OBSERVATIONS))

    result = deployment.validate_device_state(prepared())

    assert reads == list(EXPECTED_OBSERVATIONS)
    assert result.device_name == DEVICE_NAME
    assert result.status == "passed"
    assert result.validated_at.tzinfo is not None
    assert result.validated_at.utcoffset() == timezone.utc.utcoffset(result.validated_at)
    assert [(check.name, check.expected) for check in result.checks] == list(EXPECTED_CHECKS)
    assert all(check.status == "passed" for check in result.checks)
    assert all(check.observed == check.expected for check in result.checks)
    assert all(check.message is None for check in result.checks)
    assert len({check.name for check in result.checks}) == len(result.checks) == 14


@pytest.mark.parametrize(
    ("path", "observed", "failed_check"),
    (
        (HOSTNAME_PATH, "wrong-device", "system.hostname"),
        (interface_admin_path("system0"), "disable", "interface.system0.admin_state"),
        (interface_oper_path("system0"), "down", "interface.system0.oper_state"),
        (
            subinterface_admin_path("system0"),
            "disable",
            "subinterface.system0.0.admin_state",
        ),
        (
            subinterface_oper_path("system0"),
            "down",
            "subinterface.system0.0.oper_state",
        ),
        (
            ipv4_address_status_path("system0", "10.0.0.2/32"),
            None,
            "address.system0.10.0.0.2/32.status",
        ),
        (
            interface_admin_path("ethernet-1/1"),
            "disable",
            "interface.ethernet-1/1.admin_state",
        ),
        (
            interface_oper_path("ethernet-1/1"),
            "down",
            "interface.ethernet-1/1.oper_state",
        ),
        (
            subinterface_admin_path("ethernet-1/1"),
            "disable",
            "subinterface.ethernet-1/1.0.admin_state",
        ),
        (
            subinterface_oper_path("ethernet-1/1"),
            "down",
            "subinterface.ethernet-1/1.0.oper_state",
        ),
        (
            ipv4_address_status_path("ethernet-1/1", "192.0.2.1/31"),
            None,
            "address.ethernet-1/1.192.0.2.1/31.status",
        ),
        (local_asn_path(), 64512, "routing.bgp.local_asn"),
        (
            neighbor_peer_as_path("192.0.2.0"),
            64512,
            "routing.bgp.neighbor.192.0.2.0.peer_as",
        ),
        (
            neighbor_session_state_path("192.0.2.0"),
            "idle",
            "routing.bgp.neighbor.192.0.2.0.session_state",
        ),
    ),
)
def test_validation_aggregates_each_exact_mismatch_without_hiding_other_checks(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    observed: str | int | None,
    failed_check: str,
) -> None:
    configure_settings(monkeypatch)
    observations: dict[str, Any] = dict(EXPECTED_OBSERVATIONS)
    observations[path] = observed
    result = deployment._validation_result(prepared(), observations)

    assert result.status == "failed"
    assert len(result.checks) == len(EXPECTED_CHECKS)
    assert [check.name for check in result.checks if check.status == "failed"] == [
        failed_check
    ]
    failed = next(check for check in result.checks if check.name == failed_check)
    assert failed.observed == observed
    assert failed.expected == dict(EXPECTED_CHECKS)[failed_check]
    assert failed.message is not None
    assert len(failed.message) <= 256


def test_validation_omits_only_inapplicable_routed_oper_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_settings(monkeypatch)
    observations = dict(EXPECTED_OBSERVATIONS)
    observations.pop(interface_oper_path("ethernet-1/1"))
    observations.pop(subinterface_oper_path("ethernet-1/1"))
    reads = install_device_boundary(monkeypatch, observations)

    result = deployment.validate_device_state(prepared(require_oper_up=False))

    inapplicable = {
        "interface.ethernet-1/1.oper_state",
        "subinterface.ethernet-1/1.0.oper_state",
    }
    assert result.status == "passed"
    assert inapplicable.isdisjoint(check.name for check in result.checks)
    assert interface_oper_path("ethernet-1/1") not in reads
    assert subinterface_oper_path("ethernet-1/1") not in reads


@pytest.mark.parametrize(
    ("error", "expected_type", "non_retryable"),
    (
        (DeviceConnectionError("safe"), "device_unavailable", False),
        (
            DeviceAuthenticationError("safe"),
            "device_authentication_failed",
            True,
        ),
        (DevicePathError("safe"), "device_state_invalid", True),
        (DeviceResponseError("safe"), "device_state_invalid", True),
    ),
)
def test_validation_classifies_safe_device_boundary_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_type: str,
    non_retryable: bool,
) -> None:
    configure_settings(monkeypatch)
    client = MagicMock()
    client.read_native_state.side_effect = error
    monkeypatch.setattr(deployment, "_client", lambda *_: client)

    with pytest.raises(ApplicationError) as raised:
        deployment.validate_device_state(prepared())

    assert_application_error(
        raised, expected_type, non_retryable=non_retryable
    )


@pytest.mark.parametrize(
    ("path", "observed", "expected_type", "non_retryable"),
    (
        (HOSTNAME_PATH, "wrong-device", "validation_failed", True),
        (
            neighbor_session_state_path("192.0.2.0"),
            "idle",
            "validation_not_converged",
            False,
        ),
    ),
)
def test_validation_signals_permanent_mismatch_or_retryable_convergence(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    observed: str,
    expected_type: str,
    non_retryable: bool,
) -> None:
    configure_settings(monkeypatch)
    observations = dict(EXPECTED_OBSERVATIONS)
    observations[path] = observed
    install_device_boundary(monkeypatch, observations)

    with pytest.raises(ApplicationError) as raised:
        deployment.validate_device_state(prepared())

    assert_application_error(
        raised, expected_type, non_retryable=non_retryable
    )


def test_validation_failure_log_has_safe_target_check_and_category_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_settings(monkeypatch)
    monkeypatch.setattr(
        deployment.activity,
        "info",
        lambda: SimpleNamespace(workflow_id=f"deploy-device-config:{EVENT_ID}"),
    )
    observations = dict(EXPECTED_OBSERVATIONS)
    observations[neighbor_session_state_path("192.0.2.0")] = "idle"
    install_device_boundary(monkeypatch, observations)

    with caplog.at_level(logging.INFO), pytest.raises(ApplicationError):
        deployment.validate_device_state(prepared())

    record = caplog.records[-1]
    assert record.workflow_id == f"deploy-device-config:{EVENT_ID}"  # type: ignore[attr-defined]
    assert record.device_name == DEVICE_NAME  # type: ignore[attr-defined]
    assert record.activity == "validate_device_state"  # type: ignore[attr-defined]
    assert record.target == str(MANAGEMENT_ADDRESS)  # type: ignore[attr-defined]
    assert record.category == "validation_not_converged"  # type: ignore[attr-defined]
    assert record.checks == "routing.bgp.neighbor.192.0.2.0.session_state"  # type: ignore[attr-defined]
    for forbidden in ("device-password", "raw_response", "set / ", "traceback", "stack"):
        assert forbidden not in caplog.text.lower()
    temporal_logger = logging.getLogger("temporalio.activity")
    assert temporal_logger.disabled is False
    record = logging.LogRecord(
        "temporalio.activity",
        logging.WARNING,
        __file__,
        1,
        "safe SDK warning",
        (),
        (RuntimeError, RuntimeError("unsafe"), None),
    )
    assert all(log_filter.filter(record) for log_filter in temporal_logger.filters)
    assert record.exc_info is None
    assert record.stack_info is None
