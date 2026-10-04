"""Pure Feature 004 expected-state and validation comparison logic."""

from __future__ import annotations

from datetime import datetime, timezone

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
from network_automation.events.models import (
    DeviceValidationResult,
    ExpectedBgpNeighbor,
    ExpectedDeviceState,
    ExpectedInterface,
    PreparedDeployment,
    ValidationCheck,
)
from network_automation.intent.models import DeviceIntent


def expected_state_from_intent(intent: DeviceIntent) -> ExpectedDeviceState:
    """Build the accepted validation contract without rendering or writing."""

    return ExpectedDeviceState(
        device_name=intent.name,
        loopback_name="system0",
        loopback_prefix=intent.loopback.ipv4,
        routed_interfaces=tuple(
            ExpectedInterface(
                name=interface.name,
                ipv4_prefix=interface.ipv4,
                require_oper_up=True,
            )
            for interface in intent.interfaces
        ),
        local_asn=intent.bgp.local_asn,
        bgp_neighbors=tuple(
            ExpectedBgpNeighbor(address=neighbor.address, remote_asn=neighbor.remote_asn)
            for neighbor in intent.bgp.neighbors
        ),
    )


def _check(name: str, expected: str | int | bool, observed: object) -> ValidationCheck:
    passed = observed == expected and type(observed) is type(expected)
    return ValidationCheck(
        name=name,
        status="passed" if passed else "failed",
        expected=expected,
        observed=observed,
        message=None if passed else "observed device state does not match intended state",
    )


def validation_result(
    prepared: PreparedDeployment,
    observed_state: dict[str, str | int | bool | None],
) -> DeviceValidationResult:
    """Compare one bounded native-state read with the accepted expected state."""

    expected = prepared.expected_state
    checks: list[ValidationCheck] = [
        _check("system.hostname", expected.device_name, observed_state[HOSTNAME_PATH])
    ]
    interfaces = ((expected.loopback_name, expected.loopback_prefix, True),) + tuple(
        (interface.name, interface.ipv4_prefix, interface.require_oper_up)
        for interface in expected.routed_interfaces
    )
    for name, prefix, require_oper_up in interfaces:
        checks.append(
            _check(
                f"interface.{name}.admin_state",
                "enable",
                observed_state[interface_admin_path(name)],
            )
        )
        if require_oper_up:
            checks.append(
                _check(
                    f"interface.{name}.oper_state",
                    "up",
                    observed_state[interface_oper_path(name)],
                )
            )
        checks.append(
            _check(
                f"subinterface.{name}.0.admin_state",
                "enable",
                observed_state[subinterface_admin_path(name)],
            )
        )
        if require_oper_up:
            checks.append(
                _check(
                    f"subinterface.{name}.0.oper_state",
                    "up",
                    observed_state[subinterface_oper_path(name)],
                )
            )
        prefix_text = str(prefix)
        checks.append(
            _check(
                f"address.{name}.{prefix_text}.status",
                "preferred",
                observed_state[ipv4_address_status_path(name, prefix_text)],
            )
        )

    checks.append(
        _check(
            "routing.bgp.local_asn",
            expected.local_asn,
            observed_state[local_asn_path()],
        )
    )
    for neighbor in expected.bgp_neighbors:
        address = str(neighbor.address)
        checks.extend(
            (
                _check(
                    f"routing.bgp.neighbor.{address}.peer_as",
                    neighbor.remote_asn,
                    observed_state[neighbor_peer_as_path(address)],
                ),
                _check(
                    f"routing.bgp.neighbor.{address}.session_state",
                    "established",
                    observed_state[neighbor_session_state_path(address)],
                ),
            )
        )

    return DeviceValidationResult(
        device_name=expected.device_name,
        status="passed" if all(check.status == "passed" for check in checks) else "failed",
        checks=tuple(checks),
        validated_at=datetime.now(timezone.utc),
    )


__all__ = ["expected_state_from_intent", "validation_result"]
