import hashlib
import json
import os
import tempfile
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from network_automation.intent.models import BgpNeighborIntent, InterfaceIntent
from network_automation.intent.nautobot import device_intent_from_nautobot
from network_automation.rendering.srlinux import (
    UnsupportedPlatformError,
    _write_srlinux_artifact,
    _environment,
    artifact_path,
    render_srlinux,
    write_srlinux_artifact,
)

RAW = Path(__file__).parents[1] / "fixtures/nautobot/leaf01.json"
EXPECTED = Path(__file__).parents[1] / "fixtures/expected/leaf01.cfg"


def leaf01():
    return device_intent_from_nautobot(json.loads(RAW.read_text()))


def test_render_matches_reviewed_leaf01_config() -> None:
    assert render_srlinux(leaf01()) == EXPECTED.read_text()


def test_one_hundred_renders_are_byte_identical() -> None:
    outputs = {render_srlinux(leaf01()).encode() for _ in range(100)}
    assert len(outputs) == 1
    assert outputs.pop().endswith(b"\n")


def test_bgp_peer_groups_are_deterministic_for_shared_and_mixed_remote_asns() -> None:
    intent = leaf01()
    neighbors = (
        BgpNeighborIntent(address="192.0.2.5", remote_asn=65200, description="spine03"),
        BgpNeighborIntent(address="192.0.2.1", remote_asn=65100, description="spine01"),
        BgpNeighborIntent(address="192.0.2.3", remote_asn=65200, description="spine02"),
    )

    output = render_srlinux(
        intent.model_copy(update={"bgp": intent.bgp.model_copy(update={"neighbors": neighbors})})
    )
    reversed_output = render_srlinux(
        intent.model_copy(
            update={"bgp": intent.bgp.model_copy(update={"neighbors": tuple(reversed(neighbors))})}
        )
    )

    assert output == reversed_output
    assert output.count("protocols bgp afi-safi ipv4-unicast admin-state enable\n") == 1
    assert [line for line in output.splitlines() if "protocols bgp group " in line] == [
        "set / network-instance default protocols bgp group peer-as-65100 peer-as 65100",
        "set / network-instance default protocols bgp group peer-as-65200 peer-as 65200",
    ]
    assert [line for line in output.splitlines() if " peer-group " in line] == [
        "set / network-instance default protocols bgp neighbor 192.0.2.1 peer-group peer-as-65100",
        "set / network-instance default protocols bgp neighbor 192.0.2.3 peer-group peer-as-65200",
        "set / network-instance default protocols bgp neighbor 192.0.2.5 peer-group peer-as-65200",
    ]
    assert " neighbor 192.0.2.1 peer-as " not in output


def test_render_order_has_total_natural_name_tiebreaker() -> None:
    intent = leaf01()
    interfaces = (
        InterfaceIntent(name="ethernet-1/1", description="one", ipv4="198.51.100.0/31"),
        InterfaceIntent(name="ethernet-1/01", description="zero-one", ipv4="198.51.100.2/31"),
        InterfaceIntent(name="ethernet-1/10", description="ten", ipv4="198.51.100.4/31"),
        InterfaceIntent(name="ethernet-1/2", description="two", ipv4="198.51.100.6/31"),
    )
    output = render_srlinux(intent.model_copy(update={"interfaces": tuple(reversed(interfaces))}))

    positions = [output.index(f"interface {name} admin-state") for name in (
        "ethernet-1/01", "ethernet-1/1", "ethernet-1/2", "ethernet-1/10"
    )]
    assert positions == sorted(positions)


def test_platform_display_cannot_enable_unsupported_driver() -> None:
    intent = leaf01().model_copy(update={"platform": "other", "platform_display": "Nokia SR Linux"})
    with pytest.raises(UnsupportedPlatformError, match="other"):
        render_srlinux(intent)


@pytest.mark.parametrize("display", [None, "anything"])
def test_supported_driver_ignores_display(display: str | None) -> None:
    intent = leaf01().model_copy(update={"platform_display": display})
    assert render_srlinux(intent).startswith("set / system name host-name leaf01\n")


def test_artifact_path_and_atomic_write_create_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "missing" / "configs"
    path = write_srlinux_artifact(leaf01(), output_dir)

    assert path == artifact_path(leaf01(), output_dir)
    assert path == output_dir / "leaf01.cfg"
    assert path.read_bytes() == EXPECTED.read_bytes()
    assert not list(output_dir.glob("*.tmp"))


def test_internal_write_hashes_exact_ascii_bytes_before_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = EXPECTED.read_bytes()
    events: list[tuple[str, object]] = []
    real_sha256 = hashlib.sha256
    real_replace = os.replace

    def record_sha256(value: bytes):
        events.append(("hash", value))
        return real_sha256(value)

    def record_replace(source: object, destination: object) -> None:
        events.append(("replace", destination))
        real_replace(source, destination)

    monkeypatch.setattr(hashlib, "sha256", record_sha256)
    monkeypatch.setattr(os, "replace", record_replace)

    result = _write_srlinux_artifact(leaf01(), tmp_path)

    assert events == [("hash", expected), ("replace", tmp_path / "leaf01.cfg")]
    assert result.path == tmp_path / "leaf01.cfg"
    assert result.sha256 == real_sha256(expected).hexdigest()
    assert result.byte_count == len(expected)
    assert result.path.read_bytes() == expected


def test_replace_failure_preserves_existing_artifact_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "leaf01.cfg"
    target.write_text("previous\n")

    def fail_replace(source: object, destination: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        write_srlinux_artifact(leaf01(), tmp_path)

    assert target.read_text() == "previous\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_write_failure_preserves_existing_artifact_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "leaf01.cfg"
    target.write_text("previous\n")
    original = tempfile.NamedTemporaryFile

    class FailingTemporaryFile:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self._temporary = original(*args, **kwargs)
            self.name = self._temporary.name

        def __enter__(self):
            self._temporary.__enter__()
            return self

        def write(self, value: str) -> None:
            self._temporary.write(value[:10])
            raise OSError("write failed")

        def flush(self) -> None:
            self._temporary.flush()

        def __exit__(self, *args: object) -> None:
            self._temporary.__exit__(*args)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", FailingTemporaryFile)
    with pytest.raises(OSError, match="write failed"):
        write_srlinux_artifact(leaf01(), tmp_path)

    assert target.read_text() == "previous\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_unsafe_interface_name_is_quoted_without_command_injection() -> None:
    intent = leaf01()
    interface = InterfaceIntent(
        name="ethernet-1/3\nset / system name host-name injected",
        description="quoted name",
        ipv4="198.51.100.0/31",
    )

    output = render_srlinux(intent.model_copy(update={"interfaces": (interface,)}))

    assert output.count("\nset / system name host-name injected") == 0
    assert 'interface "ethernet-1/3\\nset / system name host-name injected" admin-state' in output
    assert 'interface "ethernet-1/3\\nset / system name host-name injected.0"' in output


def test_template_failure_does_not_replace_existing_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from network_automation.rendering import srlinux

    target = tmp_path / "leaf01.cfg"
    target.write_text("previous\n")

    class BrokenEnvironment:
        def get_template(self, name: str):
            raise UndefinedError(f"missing value in {name}")

    monkeypatch.setattr(srlinux, "_environment", BrokenEnvironment)
    with pytest.raises(UndefinedError, match="missing value"):
        write_srlinux_artifact(leaf01(), tmp_path)

    assert target.read_text() == "previous\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_template_environment_rejects_missing_values() -> None:
    with pytest.raises(UndefinedError):
        _environment().from_string("{{ missing }}").render()


def test_replace_failure_leaves_absent_target_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_replace(source: object, destination: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_srlinux_artifact(leaf01(), tmp_path)

    assert not (tmp_path / "leaf01.cfg").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_output_directory_creation_failure_creates_no_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "unwritable"
    original_mkdir = Path.mkdir

    def fail_mkdir(path: Path, *args: object, **kwargs: object) -> None:
        if path == output_dir:
            raise PermissionError("not writable")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    with pytest.raises(PermissionError, match="not writable"):
        write_srlinux_artifact(leaf01(), output_dir)

    assert not output_dir.exists()


def test_template_is_available_outside_repository_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert "interface system0" in render_srlinux(leaf01())
