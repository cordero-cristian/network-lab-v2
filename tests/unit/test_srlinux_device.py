import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from grpc import FutureTimeoutError, RpcError, StatusCode

from network_automation.devices import srlinux
from network_automation.devices.srlinux import (
    DeviceAuthenticationError,
    DeviceConfigurationError,
    DeviceConnectionError,
    DeviceIdentityError,
    DevicePathError,
    DevicePlatformError,
    DeviceResponseError,
    HOSTNAME_PATH,
    disable_pygnmi_logging,
    interface_admin_path,
    interface_oper_path,
    ipv4_address_status_path,
    local_asn_path,
    neighbor_peer_as_path,
    neighbor_session_state_path,
    normalize_get_response,
    SRLinuxDeviceError,
    subinterface_admin_path,
    subinterface_oper_path,
)
from network_automation.events.models import (
    ArtifactIdentity,
    DeploymentResult,
    DeploymentTarget,
    ExpectedBgpNeighbor,
    ExpectedDeviceState,
    ExpectedInterface,
    PreparedDeployment,
)


ARTIFACT = "set / system name host-name f004-leaf01\n"
DEPLOYED_AT = datetime(2026, 9, 10, 18, 0, 4, tzinfo=timezone.utc)
PASSWORD = "test-device-password"
RAW_DEVICE_DETAIL = f"credential={PASSWORD}; artifact={ARTIFACT!r}"


class LeakyRpcError(RpcError):
    def __init__(self, code: StatusCode) -> None:
        self._code = code

    def code(self) -> StatusCode:
        return self._code

    def __str__(self) -> str:
        return RAW_DEVICE_DETAIL


def update(path: str, value: object) -> dict[str, object]:
    return {"path": path, "val": value}


def response(*notifications: dict[str, object]) -> dict[str, object]:
    return {"notification": list(notifications)}


def prepared_deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PreparedDeployment:
    monkeypatch.chdir(tmp_path)
    artifact_path = Path("artifacts/configs/f004-leaf01.cfg")
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(ARTIFACT, encoding="ascii")
    artifact_bytes = ARTIFACT.encode("ascii")
    return PreparedDeployment(
        artifact=ArtifactIdentity(
            device_name="f004-leaf01",
            artifact_path=str(artifact_path),
            sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            byte_count=len(artifact_bytes),
        ),
        target=DeploymentTarget(
            device_name="f004-leaf01",
            management_address="172.31.46.12",
            platform="nokia_srl",
            gnmi_port=57401,
            tls_mode="insecure",
        ),
        expected_state=ExpectedDeviceState(
            device_name="f004-leaf01",
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
        ),
    )


def mocked_gnmi(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock]:
    gnmi = MagicMock()
    connection = MagicMock()
    connection.__enter__.return_value = gnmi
    factory = MagicMock(return_value=connection)
    monkeypatch.setattr(srlinux, "gNMIclient", factory, raising=False)
    return factory, gnmi


def test_validation_paths_omit_inapplicable_routed_oper_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    routed = prepared.expected_state.routed_interfaces[0].model_copy(
        update={"require_oper_up": False}
    )
    prepared = prepared.model_copy(
        update={
            "expected_state": prepared.expected_state.model_copy(
                update={"routed_interfaces": (routed,)}
            )
        }
    )

    paths = srlinux.SRLinuxClient._validation_paths(prepared)

    assert interface_oper_path(routed.name) not in paths
    assert subinterface_oper_path(routed.name) not in paths
    assert interface_admin_path(routed.name) in paths
    assert ipv4_address_status_path(routed.name, str(routed.ipv4_prefix)) in paths


def configure_identity_prechecks(gnmi: MagicMock) -> None:
    gnmi.capabilities.return_value = {
        "supported_models": [{"name": "srl_nokia-system"}]
    }
    gnmi.get.return_value = response(
        {"update": [update(HOSTNAME_PATH, "f004-leaf01")]}
    )


def test_default_deployment_timestamp_is_captured_after_successful_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    configure_identity_prechecks(gnmi)
    clock = MagicMock()
    clock.now.return_value = DEPLOYED_AT
    monkeypatch.setattr(srlinux, "datetime", clock)

    def successful_set(**_: object) -> dict[str, object]:
        clock.now.assert_not_called()
        return {"response": [{"op": "UPDATE"}]}

    gnmi.set.side_effect = successful_set

    result = client().deploy(prepared)

    clock.now.assert_called_once_with(timezone.utc)
    assert result.deployed_at == DEPLOYED_AT


@pytest.mark.parametrize(
    ("inner", "error_type"),
    (
        (FutureTimeoutError(), DeviceConnectionError),
        (LeakyRpcError(StatusCode.UNAUTHENTICATED), DeviceAuthenticationError),
    ),
)
def test_classifies_real_pygnmi_wrapper_shapes_safely(
    inner: Exception,
    error_type: type[SRLinuxDeviceError],
) -> None:
    wrapper = RuntimeError(RAW_DEVICE_DETAIL)
    wrapper.__cause__ = inner

    with pytest.raises(error_type) as raised:
        client()._raise_safe_rpc_error(wrapper, operation="set")

    assert RAW_DEVICE_DETAIL not in str(raised.value)


def client() -> srlinux.SRLinuxClient:
    return srlinux.SRLinuxClient(
        username="test-user", password=PASSWORD, timeout_seconds=10
    )


def assert_logger_disabled_then_reset() -> None:
    logger = logging.getLogger("pygnmi.client")
    assert logger.disabled is True
    assert logger.propagate is False
    assert logger.level > logging.CRITICAL
    logger.disabled = False
    logger.propagate = True
    logger.setLevel(logging.DEBUG)


@pytest.mark.parametrize(
    ("requested_path", "returned_path", "value"),
    [
        (
            HOSTNAME_PATH,
            "srl_nokia-system:system/srl_nokia-system-name:name/host-name",
            "f004-spine01",
        ),
        (
            local_asn_path(),
            "srl_nokia-network-instance:network-instance[name=default]/"
            "srl_nokia-netinst-protocols:protocols/srl_nokia-bgp:bgp/autonomous-system",
            65000,
        ),
    ],
)
def test_normalizes_module_qualified_paths_and_preserves_native_leaf_types(
    requested_path: str, returned_path: str, value: str | int
) -> None:
    payload = response({"update": [update(returned_path, value)]})

    observed = normalize_get_response(payload, requested_path)

    assert observed == value
    assert type(observed) is type(value)


def test_scans_every_notification_instead_of_selecting_the_first() -> None:
    payload = response(
        {"update": [update("srl_nokia-system:system/clock/current-datetime", "ignored")]},
        {},
        {
            "update": [
                update(
                    "srl_nokia-system:system/srl_nokia-system-name:name/host-name",
                    "f004-leaf01",
                )
            ]
        },
    )

    assert normalize_get_response(payload, HOSTNAME_PATH) == "f004-leaf01"


@pytest.mark.parametrize("notification", [{}, {"timestamp": 123}])
def test_omitted_update_is_valid_absence(notification: dict[str, object]) -> None:
    assert normalize_get_response(response(notification), HOSTNAME_PATH) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"notification": None},
        {"notification": {}},
        {"notification": [None]},
        {"notification": [{"update": None}]},
        {"notification": [{"update": {}}]},
        {"notification": [{"update": [None]}]},
        {"notification": [{"update": [{}]}]},
        {"notification": [{"update": [{"path": 1, "val": "up"}]}]},
        {"notification": [{"update": [{"path": "/system/name/host-name"}]}]},
        {"notification": [{"update": [update("/system/[broken", "up")]}]},
        {"notification": [{"update": [update(HOSTNAME_PATH, {"bad": "shape"})]}]},
    ],
)
def test_rejects_malformed_native_responses_without_exposing_payload(payload: object) -> None:
    with pytest.raises(DeviceResponseError, match="invalid gNMI Get response") as raised:
        normalize_get_response(payload, HOSTNAME_PATH)

    assert repr(payload) not in str(raised.value)


@pytest.mark.parametrize(
    "requested_path",
    ["", "system//name", "/system/[broken", "/interface[name=]/admin-state"],
)
def test_rejects_invalid_requested_paths_with_a_safe_concrete_error(
    requested_path: str,
) -> None:
    with pytest.raises(DevicePathError, match="invalid native gNMI path"):
        normalize_get_response(response({}), requested_path)


@pytest.mark.parametrize("values", [("up", "up"), ("up", "down")])
def test_rejects_duplicate_and_conflicting_matching_values(
    values: tuple[str, str],
) -> None:
    payload = response(
        {"update": [update(interface_oper_path("ethernet-1/1"), values[0])]},
        {"update": [update(interface_oper_path("ethernet-1/1"), values[1])]},
    )

    with pytest.raises(DeviceResponseError, match="multiple values"):
        normalize_get_response(payload, interface_oper_path("ethernet-1/1"))


def test_address_status_path_matches_the_exact_ip_prefix_list_key() -> None:
    requested = ipv4_address_status_path("ethernet-1/1", "192.0.2.0/31")
    payload = response(
        {
            "update": [
                update(
                    "srl_nokia-interfaces:interface[name=ethernet-1/1]/"
                    "subinterface[index=0]/srl_nokia-if-ip:ipv4/"
                    "address[ip-prefix=192.0.2.0/31]/status",
                    "preferred",
                )
            ]
        }
    )

    assert requested.endswith("address[ip-prefix=192.0.2.0/31]/status")
    assert "/ip-prefix" not in requested
    assert normalize_get_response(payload, requested) == "preferred"
    assert (
        normalize_get_response(
            payload, ipv4_address_status_path("ethernet-1/1", "192.0.2.2/31")
        )
        is None
    )


def test_explicit_native_leaf_paths_cover_the_corrected_contract() -> None:
    assert HOSTNAME_PATH == "/system/name/host-name"
    assert interface_admin_path("system0") == "/interface[name=system0]/admin-state"
    assert interface_oper_path("ethernet-1/1") == "/interface[name=ethernet-1/1]/oper-state"
    assert subinterface_admin_path("system0") == (
        "/interface[name=system0]/subinterface[index=0]/admin-state"
    )
    assert subinterface_oper_path("ethernet-1/1") == (
        "/interface[name=ethernet-1/1]/subinterface[index=0]/oper-state"
    )
    assert local_asn_path() == "/network-instance[name=default]/protocols/bgp/autonomous-system"
    assert neighbor_peer_as_path("192.0.2.1") == (
        "/network-instance[name=default]/protocols/bgp/"
        "neighbor[peer-address=192.0.2.1]/peer-as"
    )
    assert neighbor_session_state_path("192.0.2.1") == (
        "/network-instance[name=default]/protocols/bgp/"
        "neighbor[peer-address=192.0.2.1]/session-state"
    )


def test_pygnmi_logger_is_disabled_without_importing_the_client() -> None:
    logger = logging.getLogger("pygnmi.client")
    logger.disabled = False
    logger.propagate = True
    logger.setLevel(logging.DEBUG)

    disable_pygnmi_logging()

    assert logger.disabled is True
    assert logger.propagate is False
    assert logger.level > logging.CRITICAL


def test_deploy_prechecks_concrete_identity_and_platform_then_uses_one_exact_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    factory, gnmi = mocked_gnmi(monkeypatch)
    rpc_order: list[str] = []

    def capabilities() -> dict[str, object]:
        assert_logger_disabled_then_reset()
        rpc_order.append("capabilities")
        return {
            "supported_models": [
                {"name": "urn:nokia.com:srlinux:general:system:srl_nokia-system"}
            ]
        }

    def get(**kwargs: object) -> dict[str, object]:
        assert_logger_disabled_then_reset()
        assert kwargs == {
            "path": [HOSTNAME_PATH],
            "datatype": "all",
            "encoding": "json_ietf",
        }
        rpc_order.append("get")
        return response({"update": [update(HOSTNAME_PATH, "f004-leaf01")]})

    def set_(**kwargs: object) -> dict[str, object]:
        assert_logger_disabled_then_reset()
        assert kwargs == {"update": [("/cli://", ARTIFACT)], "encoding": "ascii"}
        rpc_order.append("set")
        return {"response": [{"op": "UPDATE"}]}

    gnmi.capabilities.side_effect = capabilities
    gnmi.get.side_effect = get
    gnmi.set.side_effect = set_

    client = srlinux.SRLinuxClient(
        username="test-user", password="test-device-password", timeout_seconds=10
    )
    result = client.deploy(prepared, deployed_at=DEPLOYED_AT)

    factory.assert_called_once_with(
        target=("172.31.46.12", 57401),
        username="test-user",
        password="test-device-password",
        insecure=True,
        timeout=10,
    )
    assert rpc_order == ["capabilities", "get", "set"]
    assert gnmi.capabilities.call_count == 1
    assert gnmi.get.call_count == 1
    assert gnmi.set.call_count == 1
    assert result == DeploymentResult(
        artifact=prepared.artifact,
        device_name="f004-leaf01",
        management_address="172.31.46.12",
        deployed_at=DEPLOYED_AT,
    )


@pytest.mark.parametrize(
    ("capabilities", "hostname", "error_type"),
    [
        ({"supported_models": [{"name": "openconfig-system"}]}, None, DevicePlatformError),
        (
            {"supported_models": [{"name": "srl_nokia-system"}]},
            "f004-spine01",
            DeviceIdentityError,
        ),
    ],
)
def test_platform_or_hostname_mismatch_prevents_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capabilities: dict[str, object],
    hostname: str | None,
    error_type: type[Exception],
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)

    def capabilities_rpc() -> dict[str, object]:
        assert_logger_disabled_then_reset()
        return capabilities

    def get(**kwargs: object) -> dict[str, object]:
        assert_logger_disabled_then_reset()
        assert kwargs["path"] == [HOSTNAME_PATH]
        return response({"update": [update(HOSTNAME_PATH, hostname)]})

    gnmi.capabilities.side_effect = capabilities_rpc
    gnmi.get.side_effect = get
    client = srlinux.SRLinuxClient(
        username="test-user", password="test-device-password", timeout_seconds=10
    )

    expected_message = (
        "device does not advertise the required SR Linux model"
        if error_type is DevicePlatformError
        else "connected device identity does not match target"
    )
    with pytest.raises(error_type, match=expected_message) as raised:
        client.deploy(prepared, deployed_at=DEPLOYED_AT)

    assert RAW_DEVICE_DETAIL not in str(raised.value)
    assert PASSWORD not in str(raised.value)
    assert ARTIFACT.strip() not in str(raised.value)
    assert gnmi.capabilities.call_count == 1
    assert gnmi.get.call_count == (1 if hostname is not None else 0)
    gnmi.set.assert_not_called()


def test_deploy_rereads_digest_before_connecting_or_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    Path(prepared.artifact.artifact_path).write_text(
        "set / system name host-name replaced\n", encoding="ascii"
    )
    factory, gnmi = mocked_gnmi(monkeypatch)
    client = srlinux.SRLinuxClient(
        username="test-user", password="test-device-password", timeout_seconds=10
    )

    with pytest.raises(SRLinuxDeviceError, match="artifact digest mismatch"):
        client.deploy(prepared, deployed_at=DEPLOYED_AT)

    factory.assert_not_called()
    gnmi.set.assert_not_called()


def test_deploy_has_no_replace_delete_fallback_or_internal_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    factory, gnmi = mocked_gnmi(monkeypatch)
    gnmi.capabilities.return_value = {
        "supported_models": [{"name": "srl_nokia-system"}]
    }
    gnmi.get.return_value = response(
        {"update": [update(HOSTNAME_PATH, "f004-leaf01")]}
    )
    gnmi.set.return_value = {"response": [{"op": "UPDATE"}]}
    client = srlinux.SRLinuxClient(
        username="test-user", password="test-device-password", timeout_seconds=10
    )

    client.deploy(prepared, deployed_at=DEPLOYED_AT)

    factory.assert_called_once()
    gnmi.set.assert_called_once_with(
        update=[("/cli://", ARTIFACT)], encoding="ascii"
    )
    assert "replace" not in gnmi.set.call_args.kwargs
    assert "delete" not in gnmi.set.call_args.kwargs
    assert not hasattr(client, "retry")


def test_deploying_the_same_artifact_twice_repeats_the_same_keyed_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    factory, gnmi = mocked_gnmi(monkeypatch)
    gnmi.capabilities.return_value = {
        "supported_models": [{"name": "srl_nokia-system"}]
    }
    gnmi.get.return_value = response(
        {"update": [update(HOSTNAME_PATH, "f004-leaf01")]}
    )
    gnmi.set.return_value = {"response": [{"op": "UPDATE"}]}
    client = srlinux.SRLinuxClient(
        username="test-user", password="test-device-password", timeout_seconds=10
    )

    first = client.deploy(prepared, deployed_at=DEPLOYED_AT)
    second = client.deploy(prepared, deployed_at=DEPLOYED_AT)

    assert first == second
    assert factory.call_count == 2
    assert gnmi.set.call_args_list == [
        call(update=[("/cli://", ARTIFACT)], encoding="ascii"),
        call(update=[("/cli://", ARTIFACT)], encoding="ascii"),
    ]
    assert ARTIFACT.splitlines() == [
        "set / system name host-name f004-leaf01"
    ]


def test_reads_every_required_native_leaf_once_with_exact_address_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    factory, gnmi = mocked_gnmi(monkeypatch)
    expected_paths = [
        HOSTNAME_PATH,
        interface_admin_path("system0"),
        interface_oper_path("system0"),
        subinterface_admin_path("system0"),
        subinterface_oper_path("system0"),
        ipv4_address_status_path("system0", "10.0.0.2/32"),
        interface_admin_path("ethernet-1/1"),
        interface_oper_path("ethernet-1/1"),
        subinterface_admin_path("ethernet-1/1"),
        subinterface_oper_path("ethernet-1/1"),
        ipv4_address_status_path("ethernet-1/1", "192.0.2.1/31"),
        local_asn_path(),
        neighbor_peer_as_path("192.0.2.0"),
        neighbor_session_state_path("192.0.2.0"),
    ]
    values: dict[str, str | int] = {
        HOSTNAME_PATH: "f004-leaf01",
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

    def get(**kwargs: object) -> dict[str, object]:
        assert_logger_disabled_then_reset()
        path = kwargs["path"]
        assert isinstance(path, list) and len(path) == 1
        assert kwargs == {
            "path": path,
            "datatype": (
                "all"
                if path[0] == HOSTNAME_PATH
                or path[0].endswith("/admin-state")
                or path[0] == local_asn_path()
                or path[0].endswith("/peer-as")
                else "state"
            ),
            "encoding": "json_ietf",
        }
        requested_path = path[0]
        assert isinstance(requested_path, str)
        return response({"update": [update(requested_path, values[requested_path])]})

    gnmi.get.side_effect = get
    client = srlinux.SRLinuxClient(
        username="test-user", password="test-device-password", timeout_seconds=10
    )

    observed = client.read_native_state(prepared)

    factory.assert_called_once()
    assert gnmi.get.call_args_list == [
        call(
            path=[path],
            datatype=(
                "all"
                if path == HOSTNAME_PATH
                or path.endswith("/admin-state")
                or path == local_asn_path()
                or path.endswith("/peer-as")
                else "state"
            ),
            encoding="json_ietf",
        )
        for path in expected_paths
    ]
    assert observed == values
    requested_paths = [item.kwargs["path"][0] for item in gnmi.get.call_args_list]
    assert all("/ip-prefix" not in path for path in requested_paths)
    assert all(
        "address[" not in path or "[ip-prefix=" in path and path.endswith("]/status")
        for path in requested_paths
    )


@pytest.mark.parametrize(
    "error",
    [
        LeakyRpcError(StatusCode.UNAVAILABLE),
        LeakyRpcError(StatusCode.DEADLINE_EXCEEDED),
        ConnectionRefusedError(RAW_DEVICE_DETAIL),
    ],
    ids=["unavailable", "deadline-exceeded", "connection-refused"],
)
def test_deploy_classifies_transient_connection_failures_without_leaking_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    configure_identity_prechecks(gnmi)
    gnmi.set.side_effect = error

    with pytest.raises(
        DeviceConnectionError, match="^device gNMI endpoint is unavailable$"
    ) as raised:
        client().deploy(prepared, deployed_at=DEPLOYED_AT)

    assert gnmi.set.call_count == 1
    assert RAW_DEVICE_DETAIL not in str(raised.value)
    assert PASSWORD not in str(raised.value)
    assert ARTIFACT.strip() not in str(raised.value)


@pytest.mark.parametrize(
    "code", [StatusCode.UNAUTHENTICATED, StatusCode.PERMISSION_DENIED]
)
def test_deploy_classifies_authentication_and_permission_failures_as_safe_permanent_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    code: StatusCode,
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    configure_identity_prechecks(gnmi)
    gnmi.set.side_effect = LeakyRpcError(code)

    with pytest.raises(
        DeviceAuthenticationError, match="^device authentication failed$"
    ) as raised:
        client().deploy(prepared, deployed_at=DEPLOYED_AT)

    assert gnmi.set.call_count == 1
    assert RAW_DEVICE_DETAIL not in str(raised.value)
    assert PASSWORD not in str(raised.value)
    assert ARTIFACT.strip() not in str(raised.value)


@pytest.mark.parametrize(
    "error",
    [
        LeakyRpcError(StatusCode.ABORTED),
        LeakyRpcError(StatusCode.INVALID_ARGUMENT),
        LeakyRpcError(StatusCode.FAILED_PRECONDITION),
        LeakyRpcError(StatusCode.UNKNOWN),
        RuntimeError(RAW_DEVICE_DETAIL),
    ],
    ids=[
        "aborted",
        "invalid-argument",
        "failed-precondition",
        "unknown-status",
        "unknown-exception",
    ],
)
def test_deploy_classifies_rejected_and_unknown_set_errors_as_safe_permanent_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    configure_identity_prechecks(gnmi)
    gnmi.set.side_effect = error

    with pytest.raises(
        DeviceConfigurationError, match="^device rejected configuration$"
    ) as raised:
        client().deploy(prepared, deployed_at=DEPLOYED_AT)

    assert gnmi.set.call_count == 1
    assert RAW_DEVICE_DETAIL not in str(raised.value)
    assert PASSWORD not in str(raised.value)
    assert ARTIFACT.strip() not in str(raised.value)


@pytest.mark.parametrize("malformed", [None, {}, {"supported_models": [RAW_DEVICE_DETAIL]}])
def test_deploy_rejects_malformed_capabilities_without_mutation_or_raw_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformed: object,
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    gnmi.capabilities.return_value = malformed

    with pytest.raises(
        DeviceResponseError, match="^invalid gNMI Capabilities response$"
    ) as raised:
        client().deploy(prepared, deployed_at=DEPLOYED_AT)

    assert repr(malformed) not in str(raised.value)
    assert RAW_DEVICE_DETAIL not in str(raised.value)
    gnmi.get.assert_not_called()
    gnmi.set.assert_not_called()


def test_deploy_rejects_malformed_identity_response_without_mutation_or_raw_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    configure_identity_prechecks(gnmi)
    malformed = {"notification": [{"update": [{"path": HOSTNAME_PATH, "val": []}]}]}
    gnmi.get.return_value = malformed

    with pytest.raises(
        DeviceResponseError, match="^invalid gNMI Get response$"
    ) as raised:
        client().deploy(prepared, deployed_at=DEPLOYED_AT)

    assert repr(malformed) not in str(raised.value)
    gnmi.set.assert_not_called()


@pytest.mark.parametrize("failing_rpc", ["capabilities", "get", "set"])
def test_pygnmi_logger_is_suppressed_immediately_before_every_failing_rpc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_rpc: str,
) -> None:
    prepared = prepared_deployment(tmp_path, monkeypatch)
    _, gnmi = mocked_gnmi(monkeypatch)
    configure_identity_prechecks(gnmi)

    def fail() -> None:
        assert_logger_disabled_then_reset()
        raise LeakyRpcError(StatusCode.PERMISSION_DENIED)

    def fail_with_kwargs(**_: object) -> None:
        fail()

    if failing_rpc == "capabilities":
        gnmi.capabilities.side_effect = fail
    elif failing_rpc == "get":
        gnmi.get.side_effect = fail_with_kwargs
    else:
        gnmi.set.side_effect = fail_with_kwargs

    with pytest.raises(DeviceAuthenticationError) as raised:
        client().deploy(prepared, deployed_at=DEPLOYED_AT)

    assert RAW_DEVICE_DETAIL not in str(raised.value)
    assert PASSWORD not in str(raised.value)
    assert ARTIFACT.strip() not in str(raised.value)
