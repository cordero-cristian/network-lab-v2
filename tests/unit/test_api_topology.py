import asyncio
from ipaddress import IPv4Address

from network_automation.api.devices import get_topology
from network_automation.intent.nautobot import NautobotError, NautobotTopologyInterface
from tests.unit.test_api_devices import Nautobot


class IncompletePhysicalNautobot(Nautobot):
    def list_topology_interfaces(self, devices):
        return (
            NautobotTopologyInterface(
                "leaf01", "ethernet-1/1", (), "leaf02", "ethernet-1/1"
            ),
            NautobotTopologyInterface(
                "leaf02", "ethernet-1/2", (), "leaf02", "ethernet-1/2"
            ),
        )

    def get_deployment_intent(self, name):
        raise NautobotError("intent unavailable")


def test_physical_links_require_reciprocal_non_self_endpoints() -> None:
    topology = asyncio.run(get_topology(IncompletePhysicalNautobot()))

    assert topology.links == ()
    assert len(topology.nodes) == 2
