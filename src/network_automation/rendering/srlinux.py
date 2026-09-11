"""Render and atomically write the supported SR Linux configuration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from network_automation.intent.models import DeviceIntent

SUPPORTED_PLATFORM = "nokia_srl"
BARE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class UnsupportedPlatformError(ValueError):
    """The intent does not identify the supported SR Linux platform."""


@dataclass(frozen=True)
class _ArtifactWriteResult:
    path: Path
    sha256: str
    byte_count: int


def _natural_key(name: str) -> tuple[tuple[tuple[int, int | str], ...], str, str]:
    components: list[tuple[int, int | str]] = []
    for component in re.split(r"(\d+)", name):
        components.append((0, int(component)) if component.isdigit() else (1, component.casefold()))
    return tuple(components), name.casefold(), name


def _quoted(value: str | None) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=True)


def _token(value: str) -> str:
    return value if BARE_TOKEN.fullmatch(value) else json.dumps(value, ensure_ascii=True)


def _environment() -> Environment:
    template_dir = files("network_automation").joinpath("templates", "srlinux")
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        newline_sequence="\n",
    )


def render_srlinux(intent: DeviceIntent) -> str:
    """Render validated intent using the sole supported platform contract."""

    if intent.platform != SUPPORTED_PLATFORM:
        raise UnsupportedPlatformError(f"unsupported platform identifier {intent.platform!r}")

    interfaces = sorted(intent.interfaces, key=lambda interface: _natural_key(interface.name))
    neighbors = sorted(intent.bgp.neighbors, key=lambda neighbor: int(neighbor.address))
    context = {
        "hostname": intent.name,
        "loopback": {
            "description": _quoted(intent.loopback.description),
            "address": str(intent.loopback.ipv4),
        },
        "interfaces": [
            {
                "name": _token(interface.name),
                "attachment": _token(f"{interface.name}.0"),
                "description": _quoted(interface.description),
                "address": str(interface.ipv4),
            }
            for interface in interfaces
        ],
        "bgp": {
            "local_asn": intent.bgp.local_asn,
            "router_id": str(intent.loopback.ipv4.ip),
            "peer_groups": [
                {"name": f"peer-as-{remote_asn}", "remote_asn": remote_asn}
                for remote_asn in sorted({neighbor.remote_asn for neighbor in neighbors})
            ],
            "neighbors": [
                {
                    "address": str(neighbor.address),
                    "peer_group": f"peer-as-{neighbor.remote_asn}",
                    "description": _quoted(neighbor.description),
                }
                for neighbor in neighbors
            ],
        },
    }
    rendered = _environment().get_template("config.j2").render(**context)
    return rendered.rstrip("\n") + "\n"


def artifact_path(intent: DeviceIntent, output_dir: Path = Path("artifacts/configs")) -> Path:
    return Path(output_dir) / f"{intent.name}.cfg"


def write_srlinux_artifact(
    intent: DeviceIntent, output_dir: Path = Path("artifacts/configs")
) -> Path:
    """Render fully, then replace the deterministic target atomically."""

    return _write_srlinux_artifact(intent, output_dir).path


def _write_srlinux_artifact(
    intent: DeviceIntent, output_dir: Path = Path("artifacts/configs")
) -> _ArtifactWriteResult:
    """Write an artifact and retain the identity of the exact bytes replaced."""

    rendered = render_srlinux(intent)
    rendered_bytes = rendered.encode("ascii")
    digest = hashlib.sha256(rendered_bytes).hexdigest()
    target = artifact_path(intent, output_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(rendered_bytes)
            temporary.flush()
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return _ArtifactWriteResult(
        path=target,
        sha256=digest,
        byte_count=len(rendered_bytes),
    )
