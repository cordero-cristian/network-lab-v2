from datetime import datetime, timezone
from ipaddress import IPv4Address, IPv4Interface
from uuid import UUID

import pytest
from pydantic import ValidationError

from network_automation.events.models import (
    ArtifactIdentity,
    DeploymentResult,
    DeploymentTarget,
    DeployDeviceConfigRequest,
    DeviceValidationResult,
    ExpectedBgpNeighbor,
    ExpectedDeviceState,
    ExpectedInterface,
    PreparedDeployment,
    ValidationCheck,
    deployment_workflow_id_for,
)


EVENT_ID = UUID("08660568-3d4c-4901-9a77-8a4fb0e68072")
CORRELATION_ID = UUID("eaf41a9d-9cb8-4de0-bd68-32bbc47e5030")
NOW = datetime(2026, 9, 10, 18, 0, 4, tzinfo=timezone.utc)
DIGEST = "cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887"


def artifact(**changes: object) -> ArtifactIdentity:
    values: dict[str, object] = {
        "device_name": "f004-leaf01",
        "artifact_path": "artifacts/configs/f004-leaf01.cfg",
        "sha256": DIGEST,
        "byte_count": 1248,
    }
    return ArtifactIdentity.model_validate(values | changes)


def target(**changes: object) -> DeploymentTarget:
    values: dict[str, object] = {
        "device_name": "f004-leaf01",
        "management_address": "172.31.46.12",
        "platform": "nokia_srl",
        "gnmi_port": 57401,
        "tls_mode": "insecure",
    }
    return DeploymentTarget.model_validate(values | changes)


def expected_state(**changes: object) -> ExpectedDeviceState:
    values: dict[str, object] = {
        "device_name": "f004-leaf01",
        "loopback_name": "system0",
        "loopback_prefix": "10.0.0.2/32",
        "routed_interfaces": (
            {
                "name": "ethernet-1/1",
                "ipv4_prefix": "192.0.2.1/31",
                "require_oper_up": True,
            },
        ),
        "local_asn": 65001,
        "bgp_neighbors": ({"address": "192.0.2.0", "remote_asn": 65000},),
    }
    return ExpectedDeviceState.model_validate(values | changes)


def test_deployment_activity_models_construct_exact_typed_payloads() -> None:
    request = DeployDeviceConfigRequest(
        operation="deploy",
        event_id=EVENT_ID,
        correlation_id=CORRELATION_ID,
        device_name="f004-leaf01",
    )
    prepared = PreparedDeployment(
        artifact=artifact(), target=target(), expected_state=expected_state()
    )
    result = DeploymentResult(
        artifact=artifact(),
        device_name="f004-leaf01",
        management_address=IPv4Address("172.31.46.12"),
        deployed_at=NOW,
    )

    assert request.operation == "deploy"
    assert deployment_workflow_id_for(EVENT_ID) == f"deploy-device-config:{EVENT_ID}"
    assert prepared.target.management_address == IPv4Address("172.31.46.12")
    assert prepared.expected_state.loopback_prefix == IPv4Interface("10.0.0.2/32")
    assert result.artifact.sha256 == DIGEST
    assert "password" not in prepared.model_dump()
    assert "artifact_content" not in prepared.model_dump()


def test_deployment_models_are_frozen_strict_and_reject_unknown_fields() -> None:
    request = DeployDeviceConfigRequest(
        operation="deploy",
        event_id=EVENT_ID,
        correlation_id=CORRELATION_ID,
        device_name="f004-leaf01",
    )

    with pytest.raises(ValidationError):
        request.device_name = "f004-spine01"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        DeployDeviceConfigRequest.model_validate(request.model_dump() | {"source": "cli"})
    with pytest.raises(ValidationError):
        DeployDeviceConfigRequest.model_validate(
            request.model_dump() | {"operation": "render"}
        )
    with pytest.raises(ValidationError):
        ArtifactIdentity.model_validate(
            artifact().model_dump() | {"byte_count": "1248"}
        )
    with pytest.raises(ValidationError):
        ExpectedInterface(
            name="ethernet-1/1",
            ipv4_prefix="192.0.2.1/31",
            require_oper_up=1,
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"artifact_path": "artifacts/configs/f004-spine01.cfg"},
        {"artifact_path": "/artifacts/configs/f004-leaf01.cfg"},
        {"sha256": "A" * 64},
        {"sha256": "0" * 63},
        {"byte_count": 0},
        {"byte_count": 1024 * 1024 + 1},
    ),
)
def test_artifact_identity_enforces_device_digest_and_safe_size(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        artifact(**changes)


@pytest.mark.parametrize(
    "changes",
    (
        {"management_address": "2001:db8::1"},
        {"management_address": "172.31.46.12/24"},
        {"platform": "ios"},
        {"gnmi_port": 0},
        {"gnmi_port": 65536},
        {"tls_mode": "secure"},
    ),
)
def test_target_accepts_only_the_normalized_srlinux_lab_endpoint(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        target(**changes)


def test_prepared_deployment_requires_one_matching_device() -> None:
    with pytest.raises(ValidationError):
        PreparedDeployment(
            artifact=artifact(),
            target=target(device_name="f004-spine01"),
            expected_state=expected_state(),
        )


def test_prepared_deployment_round_trips_through_strict_json() -> None:
    prepared = PreparedDeployment(
        artifact=artifact(), target=target(), expected_state=expected_state()
    )

    assert PreparedDeployment.model_validate_json(prepared.model_dump_json()) == prepared


def test_expected_state_enforces_safe_bounds_and_unique_ordered_members() -> None:
    state = expected_state()
    assert state.routed_interfaces == (
        ExpectedInterface(
            name="ethernet-1/1",
            ipv4_prefix="192.0.2.1/31",
            require_oper_up=True,
        ),
    )
    assert state.bgp_neighbors == (
        ExpectedBgpNeighbor(address="192.0.2.0", remote_asn=65000),
    )

    with pytest.raises(ValidationError):
        expected_state(routed_interfaces=state.routed_interfaces * 2)
    with pytest.raises(ValidationError):
        expected_state(bgp_neighbors=state.bgp_neighbors * 2)
    with pytest.raises(ValidationError):
        expected_state(local_asn=0)


def test_expected_state_cannot_exceed_validation_result_check_bound() -> None:
    interfaces = tuple(
        {
            "name": f"ethernet-1/{index}",
            "ipv4_prefix": f"198.51.100.{index * 2}/31",
            "require_oper_up": True,
        }
        for index in range(1, 13)
    )

    assert len(expected_state(routed_interfaces=interfaces[:11]).routed_interfaces) == 11
    with pytest.raises(ValidationError, match="validation check bound"):
        expected_state(routed_interfaces=interfaces)


def test_validation_checks_and_aggregate_status_are_consistent_and_bounded() -> None:
    passed = ValidationCheck(
        name="system.hostname",
        status="passed",
        expected="f004-leaf01",
        observed="f004-leaf01",
        message=None,
    )
    failed = ValidationCheck(
        name="bgp.192.0.2.0.session",
        status="failed",
        expected="established",
        observed=None,
        message="BGP session is not established",
    )
    result = DeviceValidationResult(
        device_name="f004-leaf01",
        status="failed",
        checks=(passed, failed),
        validated_at=NOW,
    )
    assert result.checks == (passed, failed)

    for values in (
        {"status": "passed", "checks": (passed, failed)},
        {"status": "failed", "checks": (passed,)},
        {"status": "passed", "checks": ()},
        {"status": "passed", "checks": (passed,) * 65},
        {"status": "passed", "checks": (passed, passed)},
    ):
        with pytest.raises(ValidationError):
            DeviceValidationResult(
                device_name="f004-leaf01", validated_at=NOW, **values
            )

    for values in (
        {"name": "x" * 129},
        {"status": "pending"},
        {"expected": "x" * 129},
        {"message": "x" * 257},
        {"observed": ["unsafe"]},
    ):
        with pytest.raises(ValidationError):
            ValidationCheck.model_validate(passed.model_dump() | values)


def test_activity_timestamps_require_utc_and_serialize_with_z() -> None:
    result = DeploymentResult(
        artifact=artifact(),
        device_name="f004-leaf01",
        management_address="172.31.46.12",
        deployed_at=NOW,
    )
    assert result.model_dump(mode="json")["deployed_at"] == "2026-09-10T18:00:04Z"

    with pytest.raises(ValidationError):
        DeploymentResult.model_validate(
            result.model_dump() | {"deployed_at": "2026-09-10T19:00:04+01:00"}
        )
