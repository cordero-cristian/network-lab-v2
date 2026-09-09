"""Typed intent models accepted by configuration renderers."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Interface
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DeviceName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
Asn = Annotated[int, Field(strict=True, ge=1, le=4294967295)]


def _reject_numeric_address(value: object) -> object:
    if isinstance(value, (bool, int, float)):
        raise ValueError("IP address values must be strings")
    return value


InterfaceIPv4 = Annotated[IPv4Interface, BeforeValidator(_reject_numeric_address)]
NeighborIPv4 = Annotated[IPv4Address, BeforeValidator(_reject_numeric_address)]


def _optional_text(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


class IntentModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LoopbackIntent(IntentModel):
    description: NonEmptyText | None = None
    ipv4: InterfaceIPv4

    _normalize_description = field_validator("description", mode="before")(_optional_text)

    @model_validator(mode="after")
    def require_host_prefix(self) -> Self:
        if self.ipv4.network.prefixlen != 32:
            raise ValueError("loopback IPv4 address must use a /32 prefix")
        return self


class InterfaceIntent(IntentModel):
    name: NonEmptyText
    description: NonEmptyText
    ipv4: InterfaceIPv4


class BgpNeighborIntent(IntentModel):
    address: NeighborIPv4
    remote_asn: Asn
    description: NonEmptyText | None = None

    _normalize_description = field_validator("description", mode="before")(_optional_text)


class BgpIntent(IntentModel):
    local_asn: Asn
    neighbors: tuple[BgpNeighborIntent, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_neighbors(self) -> Self:
        addresses = [neighbor.address for neighbor in self.neighbors]
        if len(addresses) != len(set(addresses)):
            raise ValueError("duplicate BGP neighbor address")
        return self


class DeviceIntent(IntentModel):
    name: DeviceName
    platform: NonEmptyText
    platform_display: NonEmptyText | None = None
    role: NonEmptyText
    location: NonEmptyText | None = None
    loopback: LoopbackIntent
    interfaces: tuple[InterfaceIntent, ...] = Field(min_length=1)
    bgp: BgpIntent

    _normalize_platform_display = field_validator("platform_display", mode="before")(
        _optional_text
    )
    _normalize_location = field_validator("location", mode="before")(_optional_text)

    @model_validator(mode="after")
    def validate_aggregate_intent(self) -> Self:
        names = [interface.name for interface in self.interfaces]
        if len(names) != len(set(names)):
            raise ValueError("duplicate interface name")

        local_addresses = {self.loopback.ipv4.ip}
        local_addresses.update(interface.ipv4.ip for interface in self.interfaces)
        if any(neighbor.address in local_addresses for neighbor in self.bgp.neighbors):
            raise ValueError("BGP neighbor cannot equal a local interface address")
        return self
