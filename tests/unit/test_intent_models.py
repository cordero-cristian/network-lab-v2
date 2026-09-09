from ipaddress import IPv4Address, IPv4Interface

import pytest
from pydantic import ValidationError

from network_automation.intent.models import (
    BgpIntent,
    BgpNeighborIntent,
    DeviceIntent,
    InterfaceIntent,
    LoopbackIntent,
)


def device_intent() -> DeviceIntent:
    return DeviceIntent(
        name="leaf01",
        platform="nokia_srl",
        platform_display="Nokia SR Linux",
        role="leaf",
        location="test-site",
        loopback=LoopbackIntent(description="router id", ipv4="10.0.0.1/32"),
        interfaces=(
            InterfaceIntent(name="ethernet-1/1", description="to spine01", ipv4="192.0.2.0/31"),
            InterfaceIntent(name="ethernet-1/2", description="to spine02", ipv4="192.0.2.2/31"),
        ),
        bgp=BgpIntent(
            local_asn=65001,
            neighbors=(
                BgpNeighborIntent(address="192.0.2.1", remote_asn=65100, description="spine01"),
                BgpNeighborIntent(address="192.0.2.3", remote_asn=65200, description="spine02"),
            ),
        ),
    )


def test_valid_device_intent_uses_network_types_and_is_frozen() -> None:
    intent = device_intent()

    assert intent.loopback.ipv4 == IPv4Interface("10.0.0.1/32")
    assert intent.bgp.neighbors[0].address == IPv4Address("192.0.2.1")
    with pytest.raises(ValidationError):
        intent.name = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", [0, 4294967296, True, False])
def test_invalid_asn_is_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        BgpIntent(local_asn=value, neighbors=(BgpNeighborIntent(address="192.0.2.1", remote_asn=1),))
    with pytest.raises(ValidationError):
        BgpNeighborIntent(address="192.0.2.1", remote_asn=value)


def test_malformed_ipv4_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InterfaceIntent(name="ethernet-1/1", description="peer", ipv4="not-an-ip")


@pytest.mark.parametrize("value", [1, 1.0, True])
def test_numeric_address_values_are_rejected(value: object) -> None:
    with pytest.raises(ValidationError, match="must be strings"):
        InterfaceIntent(name="ethernet-1/1", description="peer", ipv4=value)
    with pytest.raises(ValidationError, match="must be strings"):
        BgpNeighborIntent(address=value, remote_asn=65001)


def test_loopback_requires_32() -> None:
    with pytest.raises(ValidationError, match="/32"):
        LoopbackIntent(ipv4="10.0.0.1/24")


def test_duplicate_interfaces_are_rejected() -> None:
    intent = device_intent()
    with pytest.raises(ValidationError, match="duplicate interface"):
        DeviceIntent.model_validate(
            {**intent.model_dump(), "interfaces": (intent.interfaces[0], intent.interfaces[0])}
        )


def test_duplicate_neighbors_are_rejected() -> None:
    neighbor = BgpNeighborIntent(address="192.0.2.1", remote_asn=65100)
    with pytest.raises(ValidationError, match="duplicate BGP neighbor"):
        BgpIntent(local_asn=65001, neighbors=(neighbor, neighbor))


def test_neighbor_cannot_equal_local_address() -> None:
    intent = device_intent()
    bad_bgp = BgpIntent(
        local_asn=65001,
        neighbors=(BgpNeighborIntent(address="192.0.2.0", remote_asn=65100),),
    )
    with pytest.raises(ValidationError, match="local interface address"):
        DeviceIntent.model_validate({**intent.model_dump(), "bgp": bad_bgp})


@pytest.mark.parametrize("name", ["", "bad/name", "bad name"])
def test_empty_or_unsafe_device_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError):
        DeviceIntent.model_validate({**device_intent().model_dump(), "name": name})
