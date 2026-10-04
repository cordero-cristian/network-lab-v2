"""Pure current-state configuration and operational comparison logic."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
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
from network_automation.intent.models import DeviceName


SafeText = Annotated[str, StringConstraints(min_length=1, max_length=128)]
SafeMessage = Annotated[str, StringConstraints(min_length=1, max_length=256)]
SafeScalar = (
    SafeText
    | Annotated[int, Field(strict=True)]
    | Annotated[bool, Field(strict=True)]
)
CheckCount = Annotated[int, Field(strict=True, ge=0, le=64)]
ConfigurationCategory = Literal[
    "hostname",
    "interface_admin",
    "subinterface_admin",
    "address_presence",
    "bgp_local_asn",
    "bgp_peer_as",
]
OperationalCategory = Literal[
    "interface_oper",
    "subinterface_oper",
    "address_readiness",
    "bgp_session",
]

_CONFIGURATION_MISMATCH = "configuration does not match intended state"
_OPERATIONAL_UNHEALTHY = "observed state is not operationally healthy"
_OPERATIONAL_UNAVAILABLE = "operational state is unavailable"
_INVALID_OBSERVATION = "observed device state contains an invalid leaf"


def _require_safe_text(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be timezone-aware UTC")
    return value


def _serialize_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ComparisonModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class ConfigurationCheck(ComparisonModel):
    key: SafeText
    category: ConfigurationCategory
    status: Literal["match", "mismatch"]
    expected: SafeScalar
    observed: SafeScalar | None
    message: SafeMessage | None

    _validate_key = field_validator("key")(_require_safe_text)
    _validate_expected = field_validator("expected")(
        lambda value: _require_safe_text(value) if isinstance(value, str) else value
    )
    _validate_observed = field_validator("observed")(
        lambda value: _require_safe_text(value) if isinstance(value, str) else value
    )
    _validate_message = field_validator("message")(
        lambda value: _require_safe_text(value) if value is not None else None
    )

    @model_validator(mode="after")
    def require_consistent_evidence(self) -> Self:
        matches = type(self.observed) is type(self.expected) and self.observed == self.expected
        if (self.status == "match") != matches:
            raise ValueError("configuration check status must match its evidence")
        if (self.status == "match") != (self.message is None):
            raise ValueError("configuration check message must match its status")
        return self


class OperationalHealthCheck(ComparisonModel):
    key: SafeText
    category: OperationalCategory
    status: Literal["healthy", "unhealthy", "unavailable"]
    expected: SafeScalar
    observed: SafeScalar | None
    message: SafeMessage | None

    _validate_key = field_validator("key")(_require_safe_text)
    _validate_expected = field_validator("expected")(
        lambda value: _require_safe_text(value) if isinstance(value, str) else value
    )
    _validate_observed = field_validator("observed")(
        lambda value: _require_safe_text(value) if isinstance(value, str) else value
    )
    _validate_message = field_validator("message")(
        lambda value: _require_safe_text(value) if value is not None else None
    )

    @model_validator(mode="after")
    def require_consistent_evidence(self) -> Self:
        matches = type(self.observed) is type(self.expected) and self.observed == self.expected
        expected_status = (
            "unavailable"
            if self.observed is None
            else "healthy" if matches else "unhealthy"
        )
        if self.status != expected_status:
            raise ValueError("operational check status must match its evidence")
        if (self.status == "healthy") != (self.message is None):
            raise ValueError("operational check message must match its status")
        return self


class ConfigurationDriftResult(ComparisonModel):
    device_name: DeviceName
    status: Literal["in_sync", "drifted"]
    checks: tuple[ConfigurationCheck, ...] = Field(min_length=1, max_length=64)
    matches: CheckCount
    mismatches: CheckCount
    observed_at: datetime

    _validate_observed_at = field_validator("observed_at")(_require_utc)
    _serialize_observed_at = field_serializer("observed_at")(_serialize_utc)

    @model_validator(mode="after")
    def require_consistent_result(self) -> Self:
        keys = [check.key for check in self.checks]
        if len(keys) != len(set(keys)):
            raise ValueError("configuration check keys must be unique")
        matches = sum(check.status == "match" for check in self.checks)
        mismatches = len(self.checks) - matches
        if (self.matches, self.mismatches) != (matches, mismatches):
            raise ValueError("configuration counts must match checks")
        expected_status = "in_sync" if mismatches == 0 else "drifted"
        if self.status != expected_status:
            raise ValueError("configuration status must match checks")
        return self


class OperationalHealthResult(ComparisonModel):
    device_name: DeviceName
    status: Literal["healthy", "degraded", "unavailable"]
    checks: tuple[OperationalHealthCheck, ...] = Field(min_length=1, max_length=64)
    healthy_count: CheckCount
    unhealthy_count: CheckCount
    unavailable_count: CheckCount
    observed_at: datetime

    _validate_observed_at = field_validator("observed_at")(_require_utc)
    _serialize_observed_at = field_serializer("observed_at")(_serialize_utc)

    @model_validator(mode="after")
    def require_consistent_result(self) -> Self:
        keys = [check.key for check in self.checks]
        if len(keys) != len(set(keys)):
            raise ValueError("operational check keys must be unique")
        healthy = sum(check.status == "healthy" for check in self.checks)
        unhealthy = sum(check.status == "unhealthy" for check in self.checks)
        unavailable = sum(check.status == "unavailable" for check in self.checks)
        if (self.healthy_count, self.unhealthy_count, self.unavailable_count) != (
            healthy,
            unhealthy,
            unavailable,
        ):
            raise ValueError("operational counts must match checks")
        if unavailable == len(self.checks):
            expected_status = "unavailable"
        elif unhealthy or unavailable:
            expected_status = "degraded"
        else:
            expected_status = "healthy"
        if self.status != expected_status:
            raise ValueError("operational status must match checks")
        return self


class DeviceComparison(ComparisonModel):
    device_name: DeviceName
    configuration: ConfigurationDriftResult
    operational: OperationalHealthResult
    observed_at: datetime

    _validate_observed_at = field_validator("observed_at")(_require_utc)
    _serialize_observed_at = field_serializer("observed_at")(_serialize_utc)

    @model_validator(mode="after")
    def require_atomic_comparison(self) -> Self:
        if self.configuration.device_name != self.device_name:
            raise ValueError("configuration result device must match comparison")
        if self.operational.device_name != self.device_name:
            raise ValueError("operational result device must match comparison")
        if self.configuration.observed_at != self.observed_at:
            raise ValueError("configuration timestamp must match comparison")
        if self.operational.observed_at != self.observed_at:
            raise ValueError("operational timestamp must match comparison")
        return self


def compare_device_state(
    expected: ExpectedDeviceState,
    observed: Mapping[str, object],
    observed_at: datetime,
) -> DeviceComparison:
    """Compare one expected state and one normalized observation atomically."""

    if not isinstance(observed, Mapping):
        raise ValueError(_INVALID_OBSERVATION)
    interfaces = (
        (expected.loopback_name, str(expected.loopback_prefix), True),
        *(
            (interface.name, str(interface.ipv4_prefix), interface.require_oper_up)
            for interface in expected.routed_interfaces
        ),
    )

    text_paths = [HOSTNAME_PATH]
    integer_paths = [local_asn_path()]
    for name, prefix, require_oper_up in interfaces:
        text_paths.extend((interface_admin_path(name), subinterface_admin_path(name)))
        if require_oper_up:
            text_paths.extend((interface_oper_path(name), subinterface_oper_path(name)))
        text_paths.append(ipv4_address_status_path(name, prefix))
    for neighbor in expected.bgp_neighbors:
        address = str(neighbor.address)
        integer_paths.append(neighbor_peer_as_path(address))
        text_paths.append(neighbor_session_state_path(address))

    validated: dict[str, str | int | None] = {}
    for path in text_paths:
        value = observed.get(path)
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > 128
        ):
            raise ValueError(_INVALID_OBSERVATION)
        validated[path] = value
    for path in integer_paths:
        value = observed.get(path)
        if value is not None and type(value) is not int:
            raise ValueError(_INVALID_OBSERVATION)
        validated[path] = value

    configuration_checks = [
        _configuration_check(
            key="system.hostname",
            category="hostname",
            expected=expected.device_name,
            observed=validated[HOSTNAME_PATH],
        )
    ]
    operational_checks: list[OperationalHealthCheck] = []
    for name, prefix, require_oper_up in interfaces:
        configuration_checks.extend(
            (
                _configuration_check(
                    key=f"interface.{name}.admin_state",
                    category="interface_admin",
                    expected="enable",
                    observed=validated[interface_admin_path(name)],
                ),
                _configuration_check(
                    key=f"subinterface.{name}.0.admin_state",
                    category="subinterface_admin",
                    expected="enable",
                    observed=validated[subinterface_admin_path(name)],
                ),
                _configuration_check(
                    key=f"address.{name}.{prefix}.presence",
                    category="address_presence",
                    expected=True,
                    observed=validated[ipv4_address_status_path(name, prefix)] is not None,
                ),
            )
        )
        if require_oper_up:
            operational_checks.extend(
                (
                    _operational_check(
                        key=f"interface.{name}.oper_state",
                        category="interface_oper",
                        expected="up",
                        observed=validated[interface_oper_path(name)],
                    ),
                    _operational_check(
                        key=f"subinterface.{name}.0.oper_state",
                        category="subinterface_oper",
                        expected="up",
                        observed=validated[subinterface_oper_path(name)],
                    ),
                )
            )
        operational_checks.append(
            _operational_check(
                key=f"address.{name}.{prefix}.readiness",
                category="address_readiness",
                expected="preferred",
                observed=validated[ipv4_address_status_path(name, prefix)],
            )
        )

    configuration_checks.append(
        _configuration_check(
            key="routing.bgp.local_asn",
            category="bgp_local_asn",
            expected=expected.local_asn,
            observed=validated[local_asn_path()],
        )
    )
    for neighbor in expected.bgp_neighbors:
        address = str(neighbor.address)
        configuration_checks.append(
            _configuration_check(
                key=f"routing.bgp.neighbor.{address}.peer_as",
                category="bgp_peer_as",
                expected=neighbor.remote_asn,
                observed=validated[neighbor_peer_as_path(address)],
            )
        )
        operational_checks.append(
            _operational_check(
                key=f"routing.bgp.neighbor.{address}.session_state",
                category="bgp_session",
                expected="established",
                observed=validated[neighbor_session_state_path(address)],
            )
        )

    configuration = _configuration_result(
        expected.device_name, tuple(configuration_checks), observed_at
    )
    operational = _operational_result(
        expected.device_name, tuple(operational_checks), observed_at
    )
    return DeviceComparison(
        device_name=expected.device_name,
        configuration=configuration,
        operational=operational,
        observed_at=observed_at,
    )


def _configuration_check(
    *,
    key: str,
    category: ConfigurationCategory,
    expected: str | int | bool,
    observed: str | int | bool | None,
) -> ConfigurationCheck:
    matches = type(observed) is type(expected) and observed == expected
    return ConfigurationCheck(
        key=key,
        category=category,
        status="match" if matches else "mismatch",
        expected=expected,
        observed=observed,
        message=None if matches else _CONFIGURATION_MISMATCH,
    )


def _operational_check(
    *,
    key: str,
    category: OperationalCategory,
    expected: str,
    observed: str | None,
) -> OperationalHealthCheck:
    if observed is None:
        status = "unavailable"
        message = _OPERATIONAL_UNAVAILABLE
    elif observed == expected:
        status = "healthy"
        message = None
    else:
        status = "unhealthy"
        message = _OPERATIONAL_UNHEALTHY
    return OperationalHealthCheck(
        key=key,
        category=category,
        status=status,
        expected=expected,
        observed=observed,
        message=message,
    )


def _configuration_result(
    device_name: str,
    checks: tuple[ConfigurationCheck, ...],
    observed_at: datetime,
) -> ConfigurationDriftResult:
    matches = sum(check.status == "match" for check in checks)
    mismatches = len(checks) - matches
    return ConfigurationDriftResult(
        device_name=device_name,
        status="in_sync" if mismatches == 0 else "drifted",
        checks=checks,
        matches=matches,
        mismatches=mismatches,
        observed_at=observed_at,
    )


def _operational_result(
    device_name: str,
    checks: tuple[OperationalHealthCheck, ...],
    observed_at: datetime,
) -> OperationalHealthResult:
    healthy = sum(check.status == "healthy" for check in checks)
    unhealthy = sum(check.status == "unhealthy" for check in checks)
    unavailable = sum(check.status == "unavailable" for check in checks)
    if unavailable == len(checks):
        status = "unavailable"
    elif unhealthy or unavailable:
        status = "degraded"
    else:
        status = "healthy"
    return OperationalHealthResult(
        device_name=device_name,
        status=status,
        checks=checks,
        healthy_count=healthy,
        unhealthy_count=unhealthy,
        unavailable_count=unavailable,
        observed_at=observed_at,
    )


__all__ = [
    "ConfigurationCheck",
    "ConfigurationDriftResult",
    "DeviceComparison",
    "OperationalHealthCheck",
    "OperationalHealthResult",
    "compare_device_state",
]
