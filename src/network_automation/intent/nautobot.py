"""Narrow Nautobot adapter and external-to-intent conversion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface, ip_interface
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from network_automation.intent.models import (
    BgpIntent,
    BgpNeighborIntent,
    DeviceIntent,
    InterfaceIntent,
    LoopbackIntent,
)

NON_PHYSICAL_TYPES = {"virtual", "lag", "bridge", "other"}


class NautobotError(RuntimeError):
    """A credential-safe Nautobot boundary failure."""


@dataclass(frozen=True, slots=True)
class NautobotDeploymentIntent:
    """Validated render intent and its authoritative management target."""

    intent: DeviceIntent
    management_address: IPv4Address


class NautobotClient:
    """Read only the Nautobot objects required for one device intent."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._origin = urlsplit(self._base_url)[:2]
        self._client = httpx.Client(
            headers={"Authorization": f"Token {token}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> NautobotClient:
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()

    def _safe_url(self, path_or_url: str) -> str:
        url = urljoin(self._base_url, path_or_url)
        parsed = urlsplit(url)
        if parsed[:2] != self._origin:
            raise NautobotError("Nautobot related object URL has an unexpected origin")
        return url

    def _get(
        self, path_or_url: str, *, params: Mapping[str, object] | None = None
    ) -> dict[str, Any]:
        try:
            response = self._client.get(self._safe_url(path_or_url), params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise NautobotError(
                f"Nautobot request failed ({type(exc).__name__})"
            ) from exc
        except ValueError as exc:
            raise NautobotError("Nautobot returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise NautobotError("Nautobot response must be a JSON object")
        return payload

    def get_device_data(self, name: str) -> dict[str, object]:
        page = self._get("api/dcim/devices/", params={"name": name, "limit": 2})
        results = page.get("results")
        if not isinstance(results, list) or len(results) != 1:
            raise NautobotError(f"expected exactly one Nautobot device named {name!r}")
        device = _mapping(results[0], "device")

        platform_relation = _mapping(device.get("platform"), "device platform")
        platform_url = _required_text(platform_relation.get("url"), "platform URL")
        platform = self._get(platform_url)

        role_relation = _mapping(device.get("role"), "device role")
        role_url = _required_text(role_relation.get("url"), "role URL")
        role = self._get(role_url)

        location_relation_value = device.get("location")
        if location_relation_value is None:
            location = None
        else:
            location_relation = _mapping(location_relation_value, "device location")
            location_url = _required_text(location_relation.get("url"), "location URL")
            location = self._get(location_url)

        device_id = _required_text(device.get("id"), "device id")
        interfaces: list[dict[str, object]] = []
        next_url: str | None = "api/dcim/interfaces/"
        params: Mapping[str, object] | None = {"device_id": device_id}
        while next_url is not None:
            page = self._get(next_url, params=params)
            params = None
            page_results = page.get("results")
            if not isinstance(page_results, list):
                raise NautobotError("Nautobot interface page has invalid results")
            for item in page_results:
                interface = dict(_mapping(item, "interface"))
                if interface.get("enabled") is not True or interface.get("mgmt_only") is not False:
                    interfaces.append(interface)
                    continue
                type_value = interface.get("type")
                if isinstance(type_value, Mapping):
                    interface["type"] = _required_text(
                        type_value.get("value"), "interface type value"
                    )
                relations = interface.get("ip_addresses", [])
                if not _is_sequence(relations):
                    raise NautobotError("interface ip_addresses must be a list")
                addresses: list[dict[str, object]] = []
                for relation_value in relations:
                    relation = _mapping(relation_value, "IP address relation")
                    relation_url = _required_text(relation.get("url"), "IP address URL")
                    address = self._get(relation_url)
                    addresses.append({"address": address.get("address")})
                interface["ip_addresses"] = addresses
                interfaces.append(interface)
            next_value = page.get("next")
            if next_value is not None and not isinstance(next_value, str):
                raise NautobotError("Nautobot interface page has invalid next URL")
            next_url = next_value

        return {
            "device": {
                **device,
                "platform": {
                    "network_driver": platform.get("network_driver"),
                    "display": platform.get("display"),
                },
                "role": {"display": role.get("display")},
                "location": None if location is None else {"display": location.get("display")},
            },
            "interfaces": interfaces,
        }

    def get_deployment_intent(self, name: str) -> NautobotDeploymentIntent:
        """Read render intent plus the device's authoritative primary IPv4."""

        raw = self.get_device_data(name)
        device = _mapping(raw.get("device"), "device")
        relation = _mapping(device.get("primary_ip4"), "device primary_ip4")
        relation_id = _required_text(relation.get("id"), "primary_ip4 id")
        relation_url = _required_text(relation.get("url"), "primary_ip4 URL")
        safe_relation_url = self._safe_url(relation_url)
        expected_url = self._safe_url(f"api/ipam/ip-addresses/{relation_id}/")
        if safe_relation_url != expected_url:
            raise NautobotError("primary_ip4 relation is inconsistent")

        address_data = self._get(safe_relation_url)
        if _required_text(address_data.get("id"), "primary_ip4 object id") != relation_id:
            raise NautobotError("primary_ip4 relation is inconsistent")
        address = _primary_ipv4_interface(address_data.get("address"))

        if "address" in relation:
            relation_address = _primary_ipv4_interface(relation.get("address"))
            if relation_address != address:
                raise NautobotError("primary_ip4 relation is inconsistent")

        return NautobotDeploymentIntent(
            intent=device_intent_from_nautobot(raw),
            management_address=address.ip,
        )


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NautobotError(f"{label} must be an object")
    return value


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NautobotError(f"{label} must be non-empty text")
    return value.strip()


def _optional_display(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, label)


def _required_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise NautobotError(f"{label} must be a boolean")
    return value


def _primary_ipv4_interface(value: object) -> IPv4Interface:
    try:
        parsed = ip_interface(_required_text(value, "primary_ip4 address"))
    except ValueError as exc:
        raise NautobotError("primary_ip4 address must be IPv4 interface text") from exc
    if not isinstance(parsed, IPv4Interface):
        raise NautobotError("primary_ip4 address must be IPv4 interface text")
    return parsed


def _one_address(interface: Mapping[str, Any]) -> object:
    relations = interface.get("ip_addresses")
    if not _is_sequence(relations) or len(relations) != 1:
        name = interface.get("name", "<unknown>")
        raise NautobotError(f"interface {name!r} must have exactly one IPv4 address")
    return _mapping(relations[0], "IP address").get("address")


def device_intent_from_nautobot(raw: Mapping[str, object]) -> DeviceIntent:
    """Validate one compound raw Nautobot mapping as normalized device intent."""

    device = _mapping(raw.get("device"), "device")
    platform = _mapping(device.get("platform"), "platform")
    role = _mapping(device.get("role"), "role")
    location_value = device.get("location")
    location = (
        None
        if location_value is None
        else _required_text(_mapping(location_value, "location").get("display"), "location")
    )

    interface_values = raw.get("interfaces")
    if not _is_sequence(interface_values):
        raise NautobotError("interfaces must be a list")

    loopbacks: list[LoopbackIntent] = []
    routed: list[InterfaceIntent] = []
    for value in interface_values:
        interface = _mapping(value, "interface")
        enabled = _required_bool(interface.get("enabled"), "interface enabled")
        management = _required_bool(interface.get("mgmt_only"), "interface mgmt_only")
        if not enabled or management:
            continue
        interface_type = _required_text(interface.get("type"), "interface type")
        address = _one_address(interface)
        if interface_type == "virtual":
            loopbacks.append(
                LoopbackIntent(description=interface.get("description"), ipv4=address)
            )
            continue
        if interface_type in NON_PHYSICAL_TYPES:
            raise NautobotError(f"unsupported routed interface type {interface_type!r}")
        routed.append(
            InterfaceIntent(
                name=interface.get("name"),
                description=interface.get("description"),
                ipv4=address,
            )
        )

    if len(loopbacks) != 1:
        raise NautobotError("device must have exactly one eligible virtual loopback")

    context = _mapping(device.get("local_config_context_data"), "local config context")
    namespace = _mapping(context.get("network_automation"), "network_automation context")
    bgp_data = _mapping(namespace.get("bgp"), "BGP context")
    neighbor_values = bgp_data.get("neighbors")
    if not _is_sequence(neighbor_values):
        raise NautobotError("BGP neighbors must be a list")
    neighbors = tuple(
        BgpNeighborIntent(
            address=_mapping(value, "BGP neighbor").get("address"),
            remote_asn=_mapping(value, "BGP neighbor").get("remote_asn"),
            description=_mapping(value, "BGP neighbor").get("description"),
        )
        for value in neighbor_values
    )

    return DeviceIntent(
        name=device.get("name"),
        platform=platform.get("network_driver"),
        platform_display=_optional_display(platform.get("display"), "platform display"),
        role=_required_text(role.get("display"), "role"),
        location=location,
        loopback=loopbacks[0],
        interfaces=tuple(routed),
        bgp=BgpIntent(local_asn=bgp_data.get("local_asn"), neighbors=neighbors),
    )
