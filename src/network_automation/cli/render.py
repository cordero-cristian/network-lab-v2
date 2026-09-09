"""Render one Nautobot device intent to a generated SR Linux artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from network_automation.intent.nautobot import (
    NautobotClient,
    NautobotError,
    device_intent_from_nautobot,
)
from network_automation.rendering.srlinux import (
    UnsupportedPlatformError,
    write_srlinux_artifact,
)
from network_automation.settings import LabSettings


def render_device(name: str, output_dir: Path) -> Path:
    settings = LabSettings()
    with NautobotClient(
        str(settings.nautobot_url),
        settings.nautobot_token.get_secret_value(),
        timeout=settings.probe_timeout_seconds,
    ) as client:
        raw = client.get_device_data(name)
    return write_srlinux_artifact(device_intent_from_nautobot(raw), output_dir)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (NautobotError, UnsupportedPlatformError)):
        return str(exc)
    if isinstance(exc, ValidationError):
        return "input validation failed"
    if isinstance(exc, OSError):
        return f"artifact write failed ({type(exc).__name__})"
    return f"rendering failed ({type(exc).__name__})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render one Nautobot device for SR Linux")
    parser.add_argument("device", help="exact Nautobot device name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/configs"),
        help="artifact directory (default: artifacts/configs)",
    )
    args = parser.parse_args(argv)
    try:
        path = render_device(args.device, args.output_dir)
    except Exception as exc:
        print(f"error: {_safe_error(exc)}", file=sys.stderr)
        return 1
    print(path)
    return 0
