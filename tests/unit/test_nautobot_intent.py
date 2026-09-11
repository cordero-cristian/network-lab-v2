import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from network_automation.intent.nautobot import (
    NautobotClient,
    NautobotError,
    device_intent_from_nautobot,
)
from network_automation.rendering.srlinux import render_srlinux

FIXTURE = Path(__file__).parents[1] / "fixtures/nautobot/leaf01.json"


def raw_intent() -> dict[str, object]:
    return json.loads(FIXTURE.read_text())


def deployment_transport(
    primary_ip4: object,
    *,
    ip_address: object = "192.0.2.10/24",
    ip_id: object = "management-ip",
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/dcim/devices/":
            device = deepcopy(raw_intent()["device"])
            device["id"] = "device-id"
            device["primary_ip4"] = primary_ip4
            device["platform"] = {
                "url": "http://nautobot.test/api/dcim/platforms/platform-id/"
            }
            device["role"] = {"url": "http://nautobot.test/api/extras/roles/role-id/"}
            device["location"] = {
                "url": "http://nautobot.test/api/dcim/locations/location-id/"
            }
            return httpx.Response(200, json={"results": [device]})
        if path == "/api/dcim/platforms/platform-id/":
            return httpx.Response(
                200, json={"network_driver": "nokia_srl", "display": "Nokia SR Linux"}
            )
        if path == "/api/extras/roles/role-id/":
            return httpx.Response(200, json={"display": "leaf"})
        if path == "/api/dcim/locations/location-id/":
            return httpx.Response(200, json={"display": "test-site"})
        if path == "/api/dcim/interfaces/":
            interfaces = deepcopy(raw_intent()["interfaces"])
            for index, interface in enumerate(interfaces):
                interface["ip_addresses"] = [
                    {"url": f"http://nautobot.test/api/ipam/ip-addresses/ip{index}/"}
                ]
            return httpx.Response(
                200, json={"next": None, "results": interfaces}
            )
        if path.startswith("/api/ipam/ip-addresses/"):
            address_id = path.rstrip("/").rsplit("/", 1)[-1]
            interface_addresses = {
                "ip0": "192.0.2.2/31",
                "ip1": "10.0.0.1/32",
                "ip2": "192.0.2.0/31",
            }
            if address_id in interface_addresses:
                address = interface_addresses[address_id]
                return httpx.Response(200, json={"id": address_id, "address": address})
            return httpx.Response(200, json={"id": ip_id, "address": ip_address})
        raise AssertionError(request.url)

    return httpx.MockTransport(handler)


def test_convert_raw_nautobot_data() -> None:
    intent = device_intent_from_nautobot(raw_intent())

    assert intent.name == "leaf01"
    assert intent.platform == "nokia_srl"
    assert intent.platform_display == "Nokia SR Linux"
    assert not hasattr(intent.loopback, "name")
    assert str(intent.loopback.ipv4) == "10.0.0.1/32"


@pytest.mark.parametrize("display", [None, "Arbitrary diagnostic label"])
def test_stable_platform_identifier_does_not_require_display(display: str | None) -> None:
    raw = raw_intent()
    raw["device"]["platform"]["display"] = display  # type: ignore[index]
    assert device_intent_from_nautobot(raw).platform == "nokia_srl"


def test_source_loopback_name_is_not_intent() -> None:
    first = raw_intent()
    second = deepcopy(first)
    second["interfaces"][1]["name"] = "some-other-virtual-name"  # type: ignore[index]

    assert device_intent_from_nautobot(first) == device_intent_from_nautobot(second)


def test_multiple_virtual_loopbacks_are_rejected() -> None:
    raw = raw_intent()
    duplicate = deepcopy(raw["interfaces"][1])  # type: ignore[index]
    duplicate["id"] = "another"
    duplicate["name"] = "virtual-two"
    raw["interfaces"].append(duplicate)  # type: ignore[union-attr]

    with pytest.raises(NautobotError, match="exactly one.*loopback"):
        device_intent_from_nautobot(raw)


def test_optional_whitespace_description_becomes_none() -> None:
    raw = raw_intent()
    raw["device"]["local_config_context_data"]["network_automation"]["bgp"]["neighbors"][0]["description"] = "  "  # type: ignore[index]
    raw["interfaces"][1]["description"] = "  "  # type: ignore[index]
    intent = device_intent_from_nautobot(raw)
    assert intent.bgp.neighbors[0].description is None
    assert intent.loopback.description is None


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda raw: raw["interfaces"].pop(1), "exactly one.*loopback"),
        (lambda raw: raw["interfaces"][1].update(enabled=False), "exactly one.*loopback"),
        (lambda raw: raw["interfaces"][1].update(mgmt_only=True), "exactly one.*loopback"),
        (lambda raw: raw["interfaces"][0].update(type="lag"), "unsupported routed"),
        (lambda raw: raw["interfaces"][0].update(ip_addresses=[]), "exactly one IPv4"),
        (
            lambda raw: raw["interfaces"][0].update(
                ip_addresses=[{"address": "192.0.2.2/31"}, {"address": "192.0.2.4/31"}]
            ),
            "exactly one IPv4",
        ),
    ],
)
def test_invalid_interface_state_is_rejected(mutation, match: str) -> None:
    raw = raw_intent()
    mutation(raw)
    with pytest.raises((NautobotError, ValueError), match=match):
        device_intent_from_nautobot(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw["interfaces"][0].update(description=None),
        lambda raw: raw["interfaces"][0].update(ip_addresses=[{"address": "2001:db8::1/64"}]),
        lambda raw: raw["device"].update(platform={"display": "Nokia SR Linux"}),
        lambda raw: raw["device"].update(role=None),
        lambda raw: raw["device"].update(location={}),
        lambda raw: raw["interfaces"][0].update(enabled="yes"),
    ],
)
def test_malformed_required_values_are_rejected(mutation) -> None:
    raw = raw_intent()
    mutation(raw)
    with pytest.raises((NautobotError, ValueError)):
        device_intent_from_nautobot(raw)


def test_duplicate_routed_interface_is_rejected() -> None:
    raw = raw_intent()
    duplicate = deepcopy(raw["interfaces"][0])  # type: ignore[index]
    raw["interfaces"].append(duplicate)  # type: ignore[union-attr]
    with pytest.raises(ValueError, match="duplicate interface"):
        device_intent_from_nautobot(raw)


def test_client_reads_platform_pagination_and_related_addresses() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        path = request.url.path
        if path == "/api/dcim/devices/":
            return httpx.Response(200, json={"results": [{
                "id": "device-id", "name": "leaf01",
                "platform": {"url": "http://nautobot.test/api/dcim/platforms/platform-id/"},
                "role": {"url": "http://nautobot.test/api/extras/roles/role-id/"},
                "location": {"url": "http://nautobot.test/api/dcim/locations/location-id/"},
                "local_config_context_data": {"network_automation": {"bgp": {"local_asn": 65001, "neighbors": []}}},
            }]})
        if path == "/api/dcim/platforms/platform-id/":
            return httpx.Response(200, json={"network_driver": "nokia_srl", "display": "diagnostic"})
        if path == "/api/extras/roles/role-id/":
            return httpx.Response(200, json={"display": "leaf"})
        if path == "/api/dcim/locations/location-id/":
            return httpx.Response(200, json={"display": "site"})
        if path == "/api/dcim/interfaces/" and request.url.params.get("offset") is None:
            return httpx.Response(200, json={"next": "http://nautobot.test/api/dcim/interfaces/?offset=1", "results": [{
                "id": "loop", "name": "anything", "description": "router id",
                "type": {"value": "virtual", "label": "Virtual"},
                "enabled": True, "mgmt_only": False,
                "ip_addresses": [{"url": "http://nautobot.test/api/ipam/ip-addresses/ip1/"}],
            }]})
        if path == "/api/dcim/interfaces/":
            return httpx.Response(200, json={"next": None, "results": []})
        if path == "/api/ipam/ip-addresses/ip1/":
            return httpx.Response(200, json={"address": "10.0.0.1/32"})
        raise AssertionError(request.url)

    with NautobotClient(
        "http://nautobot.test", "super-secret", transport=httpx.MockTransport(handler)
    ) as client:
        raw = client.get_device_data("leaf01")

    assert raw["device"]["platform"] == {"network_driver": "nokia_srl", "display": "diagnostic"}  # type: ignore[index]
    assert len(raw["interfaces"]) == 1  # type: ignore[arg-type]
    assert raw["interfaces"][0]["type"] == "virtual"  # type: ignore[index]
    assert any("offset=1" in call for call in calls)


@pytest.mark.parametrize("count", [0, 2])
def test_client_requires_exactly_one_device(count: int) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": [{"id": str(i)} for i in range(count)]})
    )
    with NautobotClient("http://nautobot.test", "secret", transport=transport) as client:
        with pytest.raises(NautobotError, match="exactly one"):
            client.get_device_data("leaf01")


def test_client_redacts_token_from_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("failed with super-secret", request=request)

    with NautobotClient(
        "http://nautobot.test", "super-secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(NautobotError) as error:
            client.get_device_data("leaf01")

    assert "super-secret" not in str(error.value)


@pytest.mark.parametrize("status", [401, 500])
def test_client_wraps_http_status_without_credentials(status: int) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, request=request, text="super-secret")
    )
    with NautobotClient("http://nautobot.test", "super-secret", transport=transport) as client:
        with pytest.raises(NautobotError) as error:
            client.get_device_data("leaf01")
    assert "super-secret" not in str(error.value)


def test_client_rejects_non_json_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, request=request, content=b"not-json")
    )
    with NautobotClient("http://nautobot.test", "secret", transport=transport) as client:
        with pytest.raises(NautobotError, match="invalid JSON"):
            client.get_device_data("leaf01")


def test_client_wraps_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out with super-secret", request=request)

    with NautobotClient(
        "http://nautobot.test", "super-secret", transport=httpx.MockTransport(timeout)
    ) as client:
        with pytest.raises(NautobotError, match="ReadTimeout") as error:
            client.get_device_data("leaf01")
    assert "super-secret" not in str(error.value)


@pytest.mark.parametrize("related_path", ["platform", "address"])
def test_client_wraps_related_object_failure(related_path: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/dcim/devices/":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "device-id",
                            "name": "leaf01",
                            "platform": {
                                "url": "http://nautobot.test/api/dcim/platforms/platform-id/"
                            },
                            "role": {"url": "http://nautobot.test/api/extras/roles/role-id/"},
                            "location": None,
                        }
                    ]
                },
            )
        if path == "/api/dcim/platforms/platform-id/":
            if related_path == "platform":
                return httpx.Response(500)
            return httpx.Response(200, json={"network_driver": "nokia_srl"})
        if path == "/api/extras/roles/role-id/":
            return httpx.Response(200, json={"display": "leaf"})
        if path == "/api/dcim/interfaces/":
            return httpx.Response(
                200,
                json={
                    "next": None,
                    "results": [
                        {
                            "enabled": True,
                            "mgmt_only": False,
                            "ip_addresses": [
                                {"url": "http://nautobot.test/api/ipam/ip-addresses/ip1/"}
                            ],
                        }
                    ],
                },
            )
        if path == "/api/ipam/ip-addresses/ip1/":
            return httpx.Response(500)
        raise AssertionError(request.url)

    with NautobotClient(
        "http://nautobot.test", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(NautobotError, match="StatusError"):
            client.get_device_data("leaf01")


def test_client_does_not_follow_addresses_for_excluded_interfaces() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/dcim/devices/":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "device-id",
                            "name": "leaf01",
                            "platform": {
                                "url": "http://nautobot.test/api/dcim/platforms/platform-id/"
                            },
                            "role": {"url": "http://nautobot.test/api/extras/roles/role-id/"},
                            "location": None,
                        }
                    ]
                },
            )
        if path == "/api/dcim/platforms/platform-id/":
            return httpx.Response(200, json={"network_driver": "nokia_srl"})
        if path == "/api/extras/roles/role-id/":
            return httpx.Response(200, json={"display": "leaf"})
        if path == "/api/dcim/interfaces/":
            return httpx.Response(
                200,
                json={
                    "next": None,
                    "results": [
                        {
                            "enabled": False,
                            "mgmt_only": False,
                            "type": {},
                            "ip_addresses": [
                                {"url": "http://other.invalid/api/ipam/ip-addresses/forbidden/"}
                            ],
                        }
                    ],
                },
            )
        raise AssertionError(request.url)

    with NautobotClient(
        "http://nautobot.test", "secret", transport=httpx.MockTransport(handler)
    ) as client:
        raw = client.get_device_data("leaf01")
    assert len(raw["interfaces"]) == 1  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [[], {"results": "not-a-list"}, {"results": [{}]}, {"results": [{"id": "id", "platform": []}] }],
)
def test_client_rejects_malformed_lookup_shapes(payload: object) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with NautobotClient("http://nautobot.test", "secret", transport=transport) as client:
        with pytest.raises(NautobotError):
            client.get_device_data("leaf01")


def test_client_extracts_primary_ip4_host_without_changing_render_intent() -> None:
    relation = {
        "id": "management-ip",
        "url": "http://nautobot.test/api/ipam/ip-addresses/management-ip/",
        "address": "192.0.2.10/24",
    }
    with NautobotClient(
        "http://nautobot.test",
        "secret",
        transport=deployment_transport(relation),
    ) as client:
        deployment = client.get_deployment_intent("leaf01")

    assert str(deployment.management_address) == "192.0.2.10"
    assert deployment.intent == device_intent_from_nautobot(raw_intent())
    assert render_srlinux(deployment.intent) == render_srlinux(
        device_intent_from_nautobot(raw_intent())
    )


@pytest.mark.parametrize(
    ("relation", "match"),
    [
        (None, "primary_ip4"),
        ([], "primary_ip4.*object"),
        ({"id": "management-ip"}, "primary_ip4 URL"),
        (
            {
                "id": "management-ip",
                "url": "http://nautobot.test/api/dcim/devices/management-ip/",
            },
            "relation is inconsistent",
        ),
        (
            {
                "id": "management-ip",
                "url": "https://other.invalid/api/ipam/ip-addresses/management-ip/",
            },
            "unexpected origin",
        ),
    ],
)
def test_client_rejects_missing_malformed_or_cross_origin_primary_ip4(
    relation: object, match: str
) -> None:
    with NautobotClient(
        "http://nautobot.test",
        "secret",
        transport=deployment_transport(relation),
    ) as client:
        with pytest.raises(NautobotError, match=match):
            client.get_deployment_intent("leaf01")


@pytest.mark.parametrize("address", [None, "not-an-address", "2001:db8::10/64"])
def test_client_rejects_malformed_or_non_ipv4_primary_address(address: object) -> None:
    relation = {
        "id": "management-ip",
        "url": "http://nautobot.test/api/ipam/ip-addresses/management-ip/",
    }
    with NautobotClient(
        "http://nautobot.test",
        "secret",
        transport=deployment_transport(relation, ip_address=address),
    ) as client:
        with pytest.raises(NautobotError, match="primary_ip4"):
            client.get_deployment_intent("leaf01")


@pytest.mark.parametrize(
    ("relation", "ip_id", "ip_address"),
    [
        (
            {
                "id": "management-ip",
                "url": "http://nautobot.test/api/ipam/ip-addresses/management-ip/",
            },
            "different-ip",
            "192.0.2.10/24",
        ),
        (
            {
                "id": "management-ip",
                "url": "http://nautobot.test/api/ipam/ip-addresses/management-ip/",
                "address": "192.0.2.11/24",
            },
            "management-ip",
            "192.0.2.10/24",
        ),
    ],
)
def test_client_rejects_inconsistent_primary_ip4_relation(
    relation: object, ip_id: str, ip_address: str
) -> None:
    with NautobotClient(
        "http://nautobot.test",
        "secret",
        transport=deployment_transport(relation, ip_id=ip_id, ip_address=ip_address),
    ) as client:
        with pytest.raises(NautobotError, match="primary_ip4 relation is inconsistent"):
            client.get_deployment_intent("leaf01")
