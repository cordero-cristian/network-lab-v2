from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_PATH = REPOSITORY_ROOT / "lab" / "topology.yml"
BASE_COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"
DEVICE_COMPOSE_PATH = REPOSITORY_ROOT / "compose.device-access.yaml"
QUICKSTART_PATH = (
    REPOSITORY_ROOT / "specs" / "004-srlinux-deployment-validation" / "quickstart.md"
)
BOOTSTRAP_DIRECTORY = REPOSITORY_ROOT / "lab" / "bootstrap"
DEVICE_NETWORK = "network-lab-devices-mgmt"
DEVICE_NODES = {
    "f004-spine01": "172.31.46.11",
    "f004-leaf01": "172.31.46.12",
}
PINNED_IMAGE = "ghcr.io/nokia/srlinux:26.7.2-519"
NETLAB_VERSION = "26.8.0"
CONTAINERLAB_VERSION = "0.79.0"
TEST_ENVIRONMENT = {
    "COMPOSE_PROJECT_NAME": "network-lab-device-static-test",
    "KAFKA_CLUSTER_ID": "MkU3OEVBNTcwNTJENDM2Qk",
    "LAB_KAFKA_HOST_PORT": "9092",
    "LAB_NAUTOBOT_HOST_PORT": "8000",
    "LAB_TEMPORAL_HOST_PORT": "7233",
    "LAB_TEMPORAL_UI_HOST_PORT": "8080",
    "LAB_DEVICE_USERNAME": "static-device-user",
    "LAB_DEVICE_PASSWORD": "static-device-password",
    "NAUTOBOT_DB_PASSWORD": "static-test",
    "NAUTOBOT_SECRET_KEY": "static-test",
    "NAUTOBOT_SUPERUSER_API_TOKEN": "0" * 40,
    "NAUTOBOT_SUPERUSER_PASSWORD": "static-test",
    "POSTGRES_ADMIN_PASSWORD": "static-test",
    "REDIS_PASSWORD": "static-test",
    "TEMPORAL_DB_PASSWORD": "static-test",
}


def _top_level_mapping_keys(text: str, section: str) -> set[str]:
    match = re.search(
        rf"(?ms)^{re.escape(section)}:\s*$\n(?P<body>(?:^(?:  .*|\s*)$\n?)*)",
        text,
    )
    assert match is not None, f"missing top-level {section!r} mapping"
    return set(re.findall(r"(?m)^  ([A-Za-z0-9_-]+):", match.group("body")))


def _compose_config(*paths: Path) -> dict[str, Any]:
    command = ["docker", "compose"]
    for path in paths:
        command.extend(("--file", str(path)))
    command.extend(("--profile", "*", "config", "--format", "json"))
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ | TEST_ENVIRONMENT,
    )
    return json.loads(result.stdout)


def _documented_shell_commands(text: str) -> list[str]:
    blocks = re.findall(r"(?ms)^```sh\s*$\n(.*?)^```\s*$", text)
    return [line.strip() for block in blocks for line in block.splitlines() if line.strip()]


@pytest.fixture(scope="module")
def base_compose_config() -> dict[str, Any]:
    return _compose_config(BASE_COMPOSE_PATH)


def test_topology_has_exact_pinned_nodes_link_and_management_addressing() -> None:
    topology = TOPOLOGY_PATH.read_text(encoding="ascii")

    assert re.search(r"(?m)^name:\s*feature004\s*$", topology)
    assert _top_level_mapping_keys(topology, "nodes") == set(DEVICE_NODES)
    assert topology.count(PINNED_IMAGE) == 1
    assert re.search(rf"(?m)^\s+_network:\s*{DEVICE_NETWORK}\s*$", topology)
    assert re.search(r"(?m)^\s+ipv4:\s*172\.31\.46\.0/24\s*$", topology)
    for node, address in DEVICE_NODES.items():
        node_block = re.search(
            rf"(?ms)^  {re.escape(node)}:\s*$\n(?P<body>(?:^    .*\n?)*)",
            topology,
        )
        assert node_block is not None
        assert re.search(
            rf"(?m)^\s+(?:ipv4|mgmt\.ipv4):\s*{re.escape(address)}(?:/24)?\s*$",
            node_block.group("body"),
        )

    assert len(re.findall(r"(?m)^  - interfaces:\s*$", topology)) == 1
    assert topology.count("ifname: ethernet-1/1") == 2
    for node in DEVICE_NODES:
        assert re.search(rf"(?m)^\s+- node: {re.escape(node)}\s*$", topology)


def test_topology_does_not_supply_generated_device_configuration() -> None:
    topology = TOPOLOGY_PATH.read_text(encoding="ascii")

    forbidden_keys = ("config", "startup_config", "binds")
    for key in forbidden_keys:
        assert not re.search(rf"(?m)^\s*{re.escape(key)}:\s*", topology)
    assert topology.count("startup-config:") == len(DEVICE_NODES)
    for node in DEVICE_NODES:
        relative_path = f"bootstrap/{node}.cli"
        assert f"startup-config: {relative_path}" in topology
        bootstrap = (BOOTSTRAP_DIRECTORY / f"{node}.cli").read_text(encoding="ascii")
        assert bootstrap == f"set / system name host-name {node}\n"


def test_base_compose_remains_independent_of_device_topology(
    base_compose_config: dict[str, Any],
) -> None:
    assert DEVICE_NETWORK not in base_compose_config["networks"]
    for service in base_compose_config["services"].values():
        assert DEVICE_NETWORK not in service.get("networks", {})


def test_device_override_only_attaches_read_capable_services_to_external_network(
    base_compose_config: dict[str, Any],
) -> None:
    assert DEVICE_COMPOSE_PATH.is_file(), "missing optional device-access override"
    merged = _compose_config(BASE_COMPOSE_PATH, DEVICE_COMPOSE_PATH)

    assert set(merged["services"]) == set(base_compose_config["services"])
    assert set(merged["volumes"]) == set(base_compose_config["volumes"])
    for name, service in merged["services"].items():
        base_service = base_compose_config["services"][name]
        assert service.get("volumes") == base_service.get("volumes")
        assert service.get("ports") == base_service.get("ports")
        assert service.get("expose") == base_service.get("expose")
        networks = set(service.get("networks", {}))
        if name in {"automation-worker", "automation-ui-api"}:
            assert networks == {"default", DEVICE_NETWORK}
        else:
            assert DEVICE_NETWORK not in networks

    assert set(merged["networks"]) == {"default", DEVICE_NETWORK}
    device_network = merged["networks"][DEVICE_NETWORK]
    assert device_network["name"] == DEVICE_NETWORK
    assert device_network["external"] is True
    assert set(device_network) <= {"name", "external", "ipam"}
    assert device_network.get("ipam", {}) == {}


def test_quickstart_pins_exact_device_image_and_tool_versions() -> None:
    quickstart = QUICKSTART_PATH.read_text(encoding="ascii")
    normalized = " ".join(quickstart.split())

    assert f"netlab {NETLAB_VERSION}" in normalized
    assert f"containerlab {CONTAINERLAB_VERSION}" in normalized
    assert PINNED_IMAGE in quickstart


def test_quickstart_documents_safe_separate_topology_lifecycle() -> None:
    quickstart = QUICKSTART_PATH.read_text(encoding="ascii")
    commands = _documented_shell_commands(quickstart)
    topology_up = "netlab up topology.yml -p clab --no-config"
    override_up = (
        "docker compose -f compose.yaml -f compose.device-access.yaml "
        "--profile automation up -d --no-deps --wait automation-worker event-consumer"
    )
    worker_removal = (
        "docker compose -f compose.yaml -f compose.device-access.yaml "
        "--profile automation rm -sf automation-worker"
    )
    topology_down = "netlab down --cleanup"
    clear_credentials = "unset LAB_DEVICE_USERNAME LAB_DEVICE_PASSWORD"
    base_worker_restore = (
        "docker compose --profile automation up -d --no-deps --wait "
        "automation-worker event-consumer"
    )

    for command in (
        topology_up,
        "netlab status",
        override_up,
        worker_removal,
        topology_down,
        clear_credentials,
        base_worker_restore,
    ):
        assert commands.count(command) == 1
    assert commands.count("cd lab") == 2
    assert commands.count("cd ..") == 2
    up_index = commands.index(topology_up)
    down_index = commands.index(topology_down)
    assert commands[up_index - 1 : up_index + 3] == [
        "cd lab",
        topology_up,
        "netlab status",
        "cd ..",
    ]
    assert commands[down_index - 1 : down_index + 2] == [
        "cd lab",
        topology_down,
        "cd ..",
    ]
    assert "generated files remain under `lab/`" in " ".join(quickstart.split())
    assert commands.index(topology_up) < commands.index(override_up)
    assert commands.index(worker_removal) < commands.index(topology_down)
    assert commands.index(topology_down) < commands.index(clear_credentials)
    assert commands.index(clear_credentials) < commands.index(base_worker_restore)
    assert commands.index(topology_down) < commands.index(base_worker_restore)

    documented = "\n".join(commands)
    destructive_shared_patterns = (
        r"docker compose\b.*\bdown\b",
        r"docker compose\b.*(?:--volumes|-v)(?:\s|$)",
        r"docker (?:system|volume|network)\s+(?:prune|rm)\b",
        r"kafka-topics\b.*--delete\b",
        r"temporal\b.*namespace\s+delete\b",
    )
    for pattern in destructive_shared_patterns:
        assert not re.search(pattern, documented)
    assert [command for command in commands if command.startswith("netlab down")] == [
        topology_down
    ]
