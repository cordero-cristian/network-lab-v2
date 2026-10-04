"""Narrow read-only access to the accepted SR Linux native-state operation."""

from __future__ import annotations

from network_automation.devices.srlinux import SRLinuxClient
from network_automation.events.models import PreparedDeployment


def read_srlinux_native_state(
    prepared: PreparedDeployment,
    *,
    username: str,
    password: str,
    timeout_seconds: int,
) -> dict[str, str | int | bool | None]:
    """Perform exactly one Feature 004 native-state read without exposing deployment."""

    return SRLinuxClient(
        username=username,
        password=password,
        timeout_seconds=timeout_seconds,
    ).read_native_state(prepared)


__all__ = ["read_srlinux_native_state"]
