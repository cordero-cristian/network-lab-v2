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

FIXTURE = Path(__file__).parents[1] / "fixtures/nautobot/leaf01.json"


def raw_intent() -> dict[str, object]:
    return json.loads(FIXTURE.read_text())


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
