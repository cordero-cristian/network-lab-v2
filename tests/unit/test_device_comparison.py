from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from network_automation.devices.comparison import (
    ConfigurationCheck,
    ConfigurationDriftResult,
    DeviceComparison,
    OperationalHealthCheck,
    OperationalHealthResult,
    compare_device_state,
)
from network_automation.devices.srlinux import (
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
from network_automation.events.models import ExpectedDeviceState


NOW = datetime(2026, 9, 22, 15, 30, tzinfo=timezone.utc)


def expected_state() -> ExpectedDeviceState:
    return ExpectedDeviceState(
        device_name="leaf01",
        loopback_name="system0",
        loopback_prefix="10.0.0.1/32",
        routed_interfaces=(
            {
                "name": "ethernet-1/1",
                "ipv4_prefix": "192.0.2.1/31",
                "require_oper_up": True,
            },
        ),
        local_asn=65001,
        bgp_neighbors=({"address": "192.0.2.0", "remote_asn": 65000},),
    )


def matching_observation() -> dict[str, object]:
    state = expected_state()
    observed: dict[str, object] = {
        HOSTNAME_PATH: state.device_name,
        local_asn_path(): state.local_asn,
    }
    interfaces = (
        (state.loopback_name, str(state.loopback_prefix)),
        *((interface.name, str(interface.ipv4_prefix)) for interface in state.routed_interfaces),
    )
    for name, prefix in interfaces:
        observed.update(
            {
                interface_admin_path(name): "enable",
                interface_oper_path(name): "up",
                subinterface_admin_path(name): "enable",
                subinterface_oper_path(name): "up",
                ipv4_address_status_path(name, prefix): "preferred",
            }
        )
    for neighbor in state.bgp_neighbors:
        address = str(neighbor.address)
        observed[neighbor_peer_as_path(address)] = neighbor.remote_asn
        observed[neighbor_session_state_path(address)] = "established"
    return observed


def configuration_check(**changes: object) -> ConfigurationCheck:
    values: dict[str, object] = {
        "key": "system.hostname",
        "category": "hostname",
        "status": "match",
        "expected": "leaf01",
        "observed": "leaf01",
        "message": None,
    }
    return ConfigurationCheck.model_validate(values | changes)


def health_check(**changes: object) -> OperationalHealthCheck:
    values: dict[str, object] = {
        "key": "interface.system0.oper_state",
        "category": "interface_oper",
        "status": "healthy",
        "expected": "up",
        "observed": "up",
        "message": None,
    }
    return OperationalHealthCheck.model_validate(values | changes)


def configuration_result(**changes: object) -> ConfigurationDriftResult:
    values: dict[str, object] = {
        "device_name": "leaf01",
        "status": "in_sync",
        "checks": (configuration_check(),),
        "matches": 1,
        "mismatches": 0,
        "observed_at": NOW,
    }
    return ConfigurationDriftResult.model_validate(values | changes)


def health_result(**changes: object) -> OperationalHealthResult:
    values: dict[str, object] = {
        "device_name": "leaf01",
        "status": "healthy",
        "checks": (health_check(),),
        "healthy_count": 1,
        "unhealthy_count": 0,
        "unavailable_count": 0,
        "observed_at": NOW,
    }
    return OperationalHealthResult.model_validate(values | changes)


def test_comparison_models_are_strict_frozen_and_forbid_extra_fields() -> None:
    check = configuration_check()

    with pytest.raises(ValidationError):
        check.status = "mismatch"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ConfigurationCheck.model_validate(check.model_dump() | {"severity": "high"})
    with pytest.raises(ValidationError):
        ConfigurationDriftResult.model_validate(
            configuration_result().model_dump() | {"matches": "1"}
        )


@pytest.mark.parametrize(
    ("factory", "changes"),
    (
        (configuration_check, {"key": "x" * 129}),
        (configuration_check, {"expected": "x" * 129}),
        (configuration_check, {"observed": ""}),
        (configuration_check, {"message": "x" * 257}),
        (configuration_check, {"message": ["unsafe"]}),
        (configuration_check, {"status": "match", "message": "not allowed"}),
        (configuration_check, {"status": "mismatch", "message": None}),
        (health_check, {"status": "healthy", "message": "not allowed"}),
        (health_check, {"status": "unhealthy", "message": None}),
        (health_check, {"status": "unavailable", "observed": "up"}),
    ),
)
def test_check_models_enforce_safe_scalars_and_status_evidence(
    factory: object, changes: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        factory(**changes)  # type: ignore[operator]


def test_result_models_enforce_unique_keys_derived_counts_and_status() -> None:
    mismatch = configuration_check(
        status="mismatch",
        observed="other",
        message="configuration does not match intended state",
    )
    unavailable = health_check(
        status="unavailable",
        observed=None,
        message="operational state is unavailable",
    )

    invalid_configuration = (
        {"checks": (configuration_check(), configuration_check()), "matches": 2},
        {"checks": (mismatch,), "status": "in_sync", "matches": 0, "mismatches": 1},
        {"checks": (configuration_check(),), "matches": 0},
    )
    for changes in invalid_configuration:
        with pytest.raises(ValidationError):
            configuration_result(**changes)

    invalid_health = (
        {"checks": (health_check(), health_check()), "healthy_count": 2},
        {
            "checks": (unavailable,),
            "status": "degraded",
            "healthy_count": 0,
            "unavailable_count": 1,
        },
        {"checks": (health_check(),), "unhealthy_count": 1},
    )
    for changes in invalid_health:
        with pytest.raises(ValidationError):
            health_result(**changes)


def test_models_require_utc_timestamps_and_one_bundle_identity() -> None:
    non_utc = NOW.astimezone(timezone(timedelta(hours=-4)))
    with pytest.raises(ValidationError):
        configuration_result(observed_at=non_utc)
    with pytest.raises(ValidationError):
        health_result(observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        DeviceComparison(
            device_name="other",
            configuration=configuration_result(),
            operational=health_result(),
            observed_at=NOW,
        )
    with pytest.raises(ValidationError):
        DeviceComparison(
            device_name="leaf01",
            configuration=configuration_result(),
            operational=health_result(observed_at=NOW + timedelta(seconds=1)),
            observed_at=NOW,
        )


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (local_asn_path(), True),
        (local_asn_path(), "65001"),
        (neighbor_peer_as_path("192.0.2.0"), False),
        (neighbor_peer_as_path("192.0.2.0"), "65000"),
        (HOSTNAME_PATH, 7),
        (HOSTNAME_PATH, ""),
        (HOSTNAME_PATH, " " * 3),
        (HOSTNAME_PATH, "x" * 129),
        (interface_oper_path("system0"), []),
    ),
)
def test_malformed_expected_leaf_invalidates_the_whole_comparison_safely(
    path: str, value: object
) -> None:
    observed = matching_observation()
    observed[path] = value

    with pytest.raises(ValueError) as error:
        compare_device_state(expected_state(), observed, NOW)

    message = str(error.value)
    if str(value):
        assert str(value) not in message
    assert path not in message


def test_none_is_valid_absence_evidence_not_a_malformed_leaf() -> None:
    observed = matching_observation()
    observed[HOSTNAME_PATH] = None
    observed[interface_oper_path("system0")] = None

    comparison = compare_device_state(expected_state(), observed, NOW)

    assert comparison.configuration.status == "drifted"
    assert comparison.configuration.checks[0].status == "mismatch"
    assert comparison.operational.status == "degraded"
    assert comparison.operational.checks[0].status == "unavailable"


def test_matching_state_has_deterministic_configuration_checks_and_counts() -> None:
    result = compare_device_state(expected_state(), matching_observation(), NOW).configuration

    assert result.status == "in_sync"
    assert result.matches == 9
    assert result.mismatches == 0
    assert [check.key for check in result.checks] == [
        "system.hostname",
        "interface.system0.admin_state",
        "subinterface.system0.0.admin_state",
        "address.system0.10.0.0.1/32.presence",
        "interface.ethernet-1/1.admin_state",
        "subinterface.ethernet-1/1.0.admin_state",
        "address.ethernet-1/1.192.0.2.1/31.presence",
        "routing.bgp.local_asn",
        "routing.bgp.neighbor.192.0.2.0.peer_as",
    ]


@pytest.mark.parametrize(
    "path",
    (
        HOSTNAME_PATH,
        interface_admin_path("system0"),
        interface_admin_path("ethernet-1/1"),
        subinterface_admin_path("system0"),
        subinterface_admin_path("ethernet-1/1"),
        ipv4_address_status_path("system0", "10.0.0.1/32"),
        ipv4_address_status_path("ethernet-1/1", "192.0.2.1/31"),
        local_asn_path(),
        neighbor_peer_as_path("192.0.2.0"),
    ),
)
def test_each_configuration_mismatch_is_isolated(path: str) -> None:
    observed = matching_observation()
    observed[path] = None

    result = compare_device_state(expected_state(), observed, NOW).configuration

    assert result.status == "drifted"
    assert result.matches == 8
    assert result.mismatches == 1


def test_operational_failures_and_address_readiness_are_not_drift() -> None:
    observed = matching_observation()
    observed[interface_oper_path("system0")] = "down"
    observed[ipv4_address_status_path("system0", "10.0.0.1/32")] = "duplicate"
    observed[neighbor_session_state_path("192.0.2.0")] = "idle"

    comparison = compare_device_state(expected_state(), observed, NOW)

    assert comparison.configuration.status == "in_sync"
    assert comparison.operational.status == "degraded"
    assert comparison.operational.unhealthy_count == 3


def test_configuration_equality_is_type_exact() -> None:
    observed = matching_observation()
    observed[local_asn_path()] = 65002

    comparison = compare_device_state(expected_state(), observed, NOW)

    assert comparison.configuration.status == "drifted"
    assert comparison.configuration.checks[-2].observed == 65002


def test_unexpected_keys_do_not_create_checks_or_change_results() -> None:
    baseline = compare_device_state(expected_state(), matching_observation(), NOW)
    observed = matching_observation()
    observed["/unexpected/raw/value"] = {"malformed": ["ignored"]}

    assert compare_device_state(expected_state(), observed, NOW) == baseline


def test_matching_state_has_deterministic_healthy_checks_and_counts() -> None:
    result = compare_device_state(expected_state(), matching_observation(), NOW).operational

    assert result.status == "healthy"
    assert result.healthy_count == 7
    assert result.unhealthy_count == 0
    assert result.unavailable_count == 0
    assert [check.key for check in result.checks] == [
        "interface.system0.oper_state",
        "subinterface.system0.0.oper_state",
        "address.system0.10.0.0.1/32.readiness",
        "interface.ethernet-1/1.oper_state",
        "subinterface.ethernet-1/1.0.oper_state",
        "address.ethernet-1/1.192.0.2.1/31.readiness",
        "routing.bgp.neighbor.192.0.2.0.session_state",
    ]


@pytest.mark.parametrize(
    "path",
    (
        interface_oper_path("system0"),
        interface_oper_path("ethernet-1/1"),
        subinterface_oper_path("system0"),
        subinterface_oper_path("ethernet-1/1"),
        ipv4_address_status_path("system0", "10.0.0.1/32"),
        ipv4_address_status_path("ethernet-1/1", "192.0.2.1/31"),
        neighbor_session_state_path("192.0.2.0"),
    ),
)
def test_each_operational_condition_can_be_unhealthy_or_unavailable(path: str) -> None:
    unhealthy_observed = matching_observation()
    unhealthy_observed[path] = "not-ready"
    unhealthy = compare_device_state(expected_state(), unhealthy_observed, NOW).operational
    assert unhealthy.status == "degraded"
    assert unhealthy.unhealthy_count == 1

    absent_observed = matching_observation()
    absent_observed[path] = None
    unavailable = compare_device_state(expected_state(), absent_observed, NOW).operational
    assert unavailable.status == "degraded"
    assert unavailable.unavailable_count == 1


def test_all_operational_absence_is_unavailable() -> None:
    observed = matching_observation()
    for path in tuple(observed):
        if path.endswith("/oper-state") or path.endswith("/status") or path.endswith(
            "/session-state"
        ):
            observed[path] = None

    comparison = compare_device_state(expected_state(), observed, NOW)

    assert comparison.operational.status == "unavailable"
    assert comparison.operational.healthy_count == 0
    assert comparison.operational.unhealthy_count == 0
    assert comparison.operational.unavailable_count == 7
    assert comparison.configuration.status == "drifted"


def test_compare_device_state_builds_one_atomic_independent_bundle() -> None:
    observed = matching_observation()
    observed[neighbor_peer_as_path("192.0.2.0")] = 65100
    observed[neighbor_session_state_path("192.0.2.0")] = "established"

    comparison = compare_device_state(expected_state(), observed, NOW)

    assert comparison.device_name == "leaf01"
    assert comparison.observed_at is NOW
    assert comparison.configuration.observed_at is NOW
    assert comparison.operational.observed_at is NOW
    assert comparison.configuration.status == "drifted"
    assert comparison.operational.status == "healthy"
