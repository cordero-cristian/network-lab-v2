"""SR Linux-specific gNMI paths and native response normalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import logging
from pathlib import Path

from grpc import FutureTimeoutError, RpcError, StatusCode
from pygnmi.client import gNMIclient

from network_automation.events.models import (
    DeploymentResult,
    DeploymentTarget,
    PreparedDeployment,
)

HOSTNAME_PATH = "/system/name/host-name"


class SRLinuxDeviceError(RuntimeError):
    """Base for credential-safe errors raised by the SR Linux boundary."""


class DeviceConnectionError(SRLinuxDeviceError):
    """The SR Linux gNMI endpoint could not be reached."""


class DeviceAuthenticationError(SRLinuxDeviceError):
    """The SR Linux gNMI endpoint rejected authentication or authorization."""


class DeviceIdentityError(SRLinuxDeviceError):
    """The connected device identity did not match the requested target."""


class DevicePlatformError(SRLinuxDeviceError):
    """The target did not advertise the required native SR Linux model."""


class DeviceConfigurationError(SRLinuxDeviceError):
    """The device permanently rejected a configuration transaction."""


class ArtifactMismatchError(SRLinuxDeviceError):
    """The prepared artifact bytes no longer match their durable identity."""


class DevicePathError(SRLinuxDeviceError):
    """A requested native gNMI path is invalid."""


class DeviceResponseError(SRLinuxDeviceError):
    """A gNMI response is malformed or ambiguous."""


@dataclass(frozen=True)
class _PathElement:
    name: str
    keys: tuple[tuple[str, str], ...]


class SRLinuxClient:
    """Concrete pyGNMI boundary for the supported SR Linux release."""

    def __init__(self, *, username: str, password: str, timeout_seconds: int) -> None:
        self._username = username
        self._password = password
        self._timeout_seconds = timeout_seconds

    def deploy(
        self, prepared: PreparedDeployment, *, deployed_at: datetime | None = None
    ) -> DeploymentResult:
        """Verify and apply the prepared artifact in one gNMI transaction."""

        artifact = self._read_artifact(prepared)
        target = prepared.target
        if target.platform != "nokia_srl":
            raise DevicePlatformError("target platform is not supported")

        try:
            disable_pygnmi_logging()
            with self._client(target) as client:
                disable_pygnmi_logging()
                capabilities = client.capabilities()
                self._require_native_system_model(capabilities)

                hostname = self._get(client, HOSTNAME_PATH, datatype="all")
                if hostname != target.device_name:
                    raise DeviceIdentityError("connected device identity does not match target")

                disable_pygnmi_logging()
                client.set(update=[("/cli://", artifact)], encoding="ascii")
        except SRLinuxDeviceError:
            raise
        except Exception as exc:
            self._raise_safe_rpc_error(exc, operation="set")

        return DeploymentResult(
            artifact=prepared.artifact,
            device_name=target.device_name,
            management_address=target.management_address,
            deployed_at=deployed_at or datetime.now(timezone.utc),
        )

    def read_native_state(
        self, prepared: PreparedDeployment
    ) -> dict[str, str | int | bool | None]:
        """Read every native leaf required by the validation contract once."""

        paths = self._validation_paths(prepared)
        try:
            disable_pygnmi_logging()
            with self._client(prepared.target) as client:
                return {
                    path: self._get(
                        client,
                        path,
                        datatype=_validation_datatype(path),
                    )
                    for path in paths
                }
        except SRLinuxDeviceError:
            raise
        except Exception as exc:
            self._raise_safe_rpc_error(exc, operation="get")

    def _client(self, target: DeploymentTarget) -> gNMIclient:
        return gNMIclient(
            target=(str(target.management_address), target.gnmi_port),
            username=self._username,
            password=self._password,
            insecure=True,
            timeout=self._timeout_seconds,
        )

    def _get(
        self, client: gNMIclient, path: str, *, datatype: str = "state"
    ) -> str | int | bool | None:
        try:
            disable_pygnmi_logging()
            response = client.get(
                path=[path],
                datatype=datatype,
                encoding="json_ietf",
            )
        except Exception as exc:
            self._raise_safe_rpc_error(exc, operation="get")
        return normalize_get_response(response, path)

    @staticmethod
    def _read_artifact(prepared: PreparedDeployment) -> str:
        identity = prepared.artifact
        try:
            artifact_bytes = Path(identity.artifact_path).read_bytes()
        except OSError:
            raise ArtifactMismatchError("artifact is unavailable") from None

        if sha256(artifact_bytes).hexdigest() != identity.sha256:
            raise ArtifactMismatchError("artifact digest mismatch")
        if len(artifact_bytes) != identity.byte_count:
            raise ArtifactMismatchError("artifact byte count mismatch")
        try:
            return artifact_bytes.decode("ascii")
        except UnicodeDecodeError:
            raise ArtifactMismatchError("artifact is not ASCII") from None

    @staticmethod
    def _require_native_system_model(capabilities: object) -> None:
        if not isinstance(capabilities, Mapping):
            raise DeviceResponseError("invalid gNMI Capabilities response")
        supported_models = capabilities.get("supported_models")
        if not _is_sequence(supported_models):
            raise DeviceResponseError("invalid gNMI Capabilities response")
        for model in supported_models:
            if not isinstance(model, Mapping) or not isinstance(model.get("name"), str):
                raise DeviceResponseError("invalid gNMI Capabilities response")
            if model["name"].rsplit(":", 1)[-1] == "srl_nokia-system":
                return
        raise DevicePlatformError("device does not advertise the required SR Linux model")

    @staticmethod
    def _validation_paths(prepared: PreparedDeployment) -> tuple[str, ...]:
        expected = prepared.expected_state
        paths = [HOSTNAME_PATH]
        interfaces = (
            (expected.loopback_name, str(expected.loopback_prefix), True),
            *(
                (
                    interface.name,
                    str(interface.ipv4_prefix),
                    interface.require_oper_up,
                )
                for interface in expected.routed_interfaces
            ),
        )
        for interface_name, prefix, require_oper_up in interfaces:
            paths.append(interface_admin_path(interface_name))
            if require_oper_up:
                paths.append(interface_oper_path(interface_name))
            paths.append(subinterface_admin_path(interface_name))
            if require_oper_up:
                paths.append(subinterface_oper_path(interface_name))
            paths.append(ipv4_address_status_path(interface_name, prefix))
        paths.append(local_asn_path())
        for neighbor in expected.bgp_neighbors:
            address = str(neighbor.address)
            paths.extend(
                (
                    neighbor_peer_as_path(address),
                    neighbor_session_state_path(address),
                )
            )
        return tuple(paths)

    @staticmethod
    def _raise_safe_rpc_error(exc: Exception, *, operation: str) -> None:
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            if isinstance(current, RpcError):
                code = current.code()
                if code in (StatusCode.UNAVAILABLE, StatusCode.DEADLINE_EXCEEDED):
                    raise DeviceConnectionError(
                        "device gNMI endpoint is unavailable"
                    ) from None
                if code in (StatusCode.UNAUTHENTICATED, StatusCode.PERMISSION_DENIED):
                    raise DeviceAuthenticationError("device authentication failed") from None
                if operation == "get" and code == StatusCode.INVALID_ARGUMENT:
                    raise DevicePathError("device rejected native gNMI path") from None
            if isinstance(
                current,
                (ConnectionError, TimeoutError, FutureTimeoutError, OSError),
            ):
                raise DeviceConnectionError("device gNMI endpoint is unavailable") from None
            current = current.__cause__ or current.__context__
        if operation == "set":
            raise DeviceConfigurationError("device rejected configuration") from None
        raise DeviceResponseError("device gNMI RPC failed") from None


def disable_pygnmi_logging() -> None:
    """Contain pyGNMI's response/configuration logging before an RPC is made."""

    logger = logging.getLogger("pygnmi.client")
    logger.disabled = True
    logger.propagate = False
    logger.setLevel(logging.CRITICAL + 1)


def _validation_datatype(path: str) -> str:
    if (
        path == HOSTNAME_PATH
        or path.endswith("/admin-state")
        or path == local_asn_path()
        or path.endswith("/peer-as")
    ):
        return "all"
    return "state"


def interface_admin_path(interface_name: str) -> str:
    return f"/interface[name={_path_key(interface_name)}]/admin-state"


def interface_oper_path(interface_name: str) -> str:
    return f"/interface[name={_path_key(interface_name)}]/oper-state"


def subinterface_admin_path(interface_name: str) -> str:
    return f"/interface[name={_path_key(interface_name)}]/subinterface[index=0]/admin-state"


def subinterface_oper_path(interface_name: str) -> str:
    return f"/interface[name={_path_key(interface_name)}]/subinterface[index=0]/oper-state"


def ipv4_address_status_path(interface_name: str, prefix: str) -> str:
    return (
        f"/interface[name={_path_key(interface_name)}]/subinterface[index=0]/ipv4/"
        f"address[ip-prefix={_path_key(prefix)}]/status"
    )


def local_asn_path() -> str:
    return "/network-instance[name=default]/protocols/bgp/autonomous-system"


def neighbor_peer_as_path(peer_address: str) -> str:
    return (
        "/network-instance[name=default]/protocols/bgp/"
        f"neighbor[peer-address={_path_key(peer_address)}]/peer-as"
    )


def neighbor_session_state_path(peer_address: str) -> str:
    return (
        "/network-instance[name=default]/protocols/bgp/"
        f"neighbor[peer-address={_path_key(peer_address)}]/session-state"
    )


def normalize_get_response(response: object, requested_path: str) -> str | int | bool | None:
    """Return the one native leaf value matching a semantic path, or valid absence."""

    requested = _parse_path(
        requested_path, DevicePathError, "invalid native gNMI path", allow_relative=False
    )
    if not isinstance(response, Mapping):
        raise DeviceResponseError("invalid gNMI Get response")
    notifications = response.get("notification")
    if not _is_sequence(notifications):
        raise DeviceResponseError("invalid gNMI Get response")

    values: list[str | int | bool] = []
    seen_paths: set[tuple[_PathElement, ...]] = set()
    for notification in notifications:
        if not isinstance(notification, Mapping):
            raise DeviceResponseError("invalid gNMI Get response")
        updates = notification.get("update", [])
        if not _is_sequence(updates):
            raise DeviceResponseError("invalid gNMI Get response")
        for update in updates:
            if not isinstance(update, Mapping):
                raise DeviceResponseError("invalid gNMI Get response")
            path = update.get("path")
            if not isinstance(path, str) or "val" not in update:
                raise DeviceResponseError("invalid gNMI Get response")
            normalized = _parse_path(
                path,
                DeviceResponseError,
                "invalid gNMI Get response",
                allow_relative=True,
            )
            if normalized in seen_paths:
                raise DeviceResponseError("gNMI Get response contains multiple values")
            seen_paths.add(normalized)

            value = update["val"]
            if type(value) not in (str, int, bool):
                raise DeviceResponseError("invalid gNMI Get response")
            if normalized == requested:
                values.append(value)

    if len(values) > 1:
        raise DeviceResponseError("gNMI Get response contains multiple values")
    return values[0] if values else None


def _path_key(value: str) -> str:
    if not isinstance(value, str) or not value or any(char in value for char in "[]="):
        raise DevicePathError("invalid native gNMI path key")
    return value


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _parse_path(
    path: str,
    error_type: type[SRLinuxDeviceError],
    message: str,
    *,
    allow_relative: bool,
) -> tuple[_PathElement, ...]:
    try:
        parts = _split_path(path, allow_relative=allow_relative)
        return tuple(_parse_element(part) for part in parts)
    except (TypeError, ValueError) as exc:
        raise error_type(message) from exc


def _split_path(path: str, *, allow_relative: bool) -> tuple[str, ...]:
    if not isinstance(path, str) or not path or path == "/":
        raise ValueError
    if not path.startswith("/"):
        if not allow_relative:
            raise ValueError
        path = "/" + path

    parts: list[str] = []
    start = 1
    bracket_depth = 0
    for index, character in enumerate(path[1:], start=1):
        if character == "[":
            bracket_depth += 1
            if bracket_depth > 1:
                raise ValueError
        elif character == "]":
            bracket_depth -= 1
            if bracket_depth < 0:
                raise ValueError
        elif character == "/" and bracket_depth == 0:
            if index == start:
                raise ValueError
            parts.append(path[start:index])
            start = index + 1
    if bracket_depth != 0 or start == len(path):
        raise ValueError
    parts.append(path[start:])
    return tuple(parts)


def _parse_element(element: str) -> _PathElement:
    bracket = element.find("[")
    raw_name = element if bracket < 0 else element[:bracket]
    name = _local_name(raw_name)
    remainder = "" if bracket < 0 else element[bracket:]
    keys: list[tuple[str, str]] = []

    while remainder:
        if not remainder.startswith("["):
            raise ValueError
        closing = remainder.find("]")
        if closing < 0:
            raise ValueError
        expression = remainder[1:closing]
        raw_key, separator, value = expression.partition("=")
        if not separator or not value or "[" in expression:
            raise ValueError
        keys.append((_local_name(raw_key), value))
        remainder = remainder[closing + 1 :]

    if len(keys) != len({key for key, _ in keys}):
        raise ValueError
    return _PathElement(name=name, keys=tuple(sorted(keys)))


def _local_name(name: str) -> str:
    local = name.rsplit(":", 1)[-1]
    if not local or any(character in local for character in "/[]="):
        raise ValueError
    return local
