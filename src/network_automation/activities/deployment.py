"""External preparation, deployment, and device-validation activities."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import httpx
from jinja2 import TemplateError
from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError

from network_automation.devices import srlinux
from network_automation.devices.srlinux import (
    ArtifactMismatchError,
    DeviceAuthenticationError,
    DeviceConfigurationError,
    DeviceConnectionError,
    DeviceIdentityError,
    DevicePathError,
    DevicePlatformError,
    DeviceResponseError,
)
from network_automation.devices.validation import (
    expected_state_from_intent,
    validation_result as compare_device_state,
)
from network_automation.events.models import (
    ArtifactIdentity,
    DeploymentResult,
    DeploymentTarget,
    DeployDeviceConfigRequest,
    DeviceValidationResult,
    PreparedDeployment,
    deployment_workflow_id_for,
)
from network_automation.intent.nautobot import NautobotClient, NautobotError
from network_automation.rendering.srlinux import _write_srlinux_artifact
from network_automation.rendering.srlinux import UnsupportedPlatformError
from network_automation.settings import LabSettings

LOGGER = logging.getLogger(__name__)
ARTIFACT_DIRECTORY = Path("artifacts/configs")
MAX_ARTIFACT_BYTES = 1024 * 1024

# Keep the name local so activity tests can replace the external boundary.
SRLinuxClient = srlinux.SRLinuxClient


def _settings() -> tuple[LabSettings, str, str]:
    settings = LabSettings()
    if settings.device_username is None or settings.device_password is None:
        raise ApplicationError(
            "device connection settings are missing",
            type="device_settings_missing",
            non_retryable=True,
        )
    return (
        settings,
        settings.device_username,
        settings.device_password.get_secret_value(),
    )


def _client(settings: LabSettings, username: str, password: str) -> Any:
    return SRLinuxClient(
        username=username,
        password=password,
        timeout_seconds=settings.device_gnmi_timeout_seconds,
    )


def _verify_artifact_shape(path: Path, device_name: str, identity: ArtifactIdentity) -> None:
    expected_path = ARTIFACT_DIRECTORY / f"{device_name}.cfg"
    if path != expected_path or identity.artifact_path != expected_path.as_posix():
        raise ApplicationError(
            "artifact path does not match the requested device",
            type="artifact_mismatch",
            non_retryable=True,
        )
    try:
        content = path.read_bytes()
    except OSError:
        raise ApplicationError(
            "artifact storage is temporarily unavailable",
            type="artifact_unavailable",
            non_retryable=False,
        ) from None
    try:
        text = content.decode("ascii")
    except UnicodeDecodeError:
        raise ApplicationError(
            "artifact is not ASCII",
            type="artifact_invalid",
            non_retryable=True,
        ) from None
    lines = text.splitlines()
    hostname = f"set / system name host-name {device_name}"
    hostname_lines = [
        line for line in lines if line.startswith("set / system name host-name ")
    ]
    if hostname_lines and hostname_lines != [hostname]:
        raise ApplicationError(
            "artifact target does not match the requested device",
            type="artifact_mismatch",
            non_retryable=True,
        )
    if (
        not 1 <= len(content) <= MAX_ARTIFACT_BYTES
        or len(content) != identity.byte_count
        or hashlib.sha256(content).hexdigest() != identity.sha256
        or not text.endswith("\n")
        or not lines
        or any(not line.startswith("set / ") for line in lines)
        or lines.count(hostname) != 1
    ):
        raise ApplicationError(
            "artifact shape is invalid",
            type="artifact_invalid",
            non_retryable=True,
        )


def _prepare_classification(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, NautobotError):
        cause = exc.__cause__
        if isinstance(cause, httpx.TransportError):
            return "nautobot_unavailable", "Nautobot is temporarily unavailable", False
        if isinstance(cause, httpx.HTTPStatusError):
            if cause.response.status_code in {408, 429} or cause.response.status_code >= 500:
                return "nautobot_unavailable", "Nautobot is temporarily unavailable", False
            return "nautobot_rejected", "Nautobot rejected the request", True
        if str(exc).startswith(("primary_ip4", "device primary_ip4")):
            return "management_address_invalid", "management address is invalid", True
        return "intent_invalid", "device intent validation failed", True
    if isinstance(exc, OSError):
        return "artifact_unavailable", "artifact storage is temporarily unavailable", False
    if isinstance(exc, (ValidationError, ValueError)):
        return "intent_invalid", "device intent validation failed", True
    if isinstance(exc, UnsupportedPlatformError):
        return "unsupported_platform", "device platform is unsupported", True
    if isinstance(exc, TemplateError):
        return "artifact_invalid", "configuration rendering failed", True
    return "intent_invalid", "deployment preparation failed", True


def _device_classification(exc: Exception, *, validating: bool) -> tuple[str, str, bool]:
    if isinstance(exc, DeviceConnectionError):
        return "device_unavailable", "device gNMI endpoint is unavailable", False
    if isinstance(exc, DeviceAuthenticationError):
        return "device_authentication_failed", "device authentication failed", True
    if validating:
        if isinstance(exc, (DevicePathError, DeviceResponseError)):
            return "device_state_invalid", "device state response is invalid", True
        return "internal_error", "device validation failed unexpectedly", True
    if isinstance(exc, ArtifactMismatchError):
        return "artifact_mismatch", "artifact no longer matches prepared identity", True
    if isinstance(exc, DeviceIdentityError):
        return "device_identity_mismatch", "connected device identity does not match target", True
    if isinstance(exc, DevicePlatformError):
        return "device_platform_mismatch", "device platform does not match target", True
    if isinstance(exc, DeviceConfigurationError):
        return "configuration_rejected", "device rejected configuration", True
    return "internal_error", "device deployment failed unexpectedly", True


class _SafeTemporalActivityFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def _contain_temporal_activity_logging() -> None:
    temporal_logger = logging.getLogger("temporalio.activity")
    if not any(
        isinstance(log_filter, _SafeTemporalActivityFilter)
        for log_filter in temporal_logger.filters
    ):
        temporal_logger.addFilter(_SafeTemporalActivityFilter())


def _raise_classified(error_type: str, message: str, non_retryable: bool) -> None:
    _contain_temporal_activity_logging()
    raise ApplicationError(
        message,
        type=error_type,
        non_retryable=non_retryable,
    ) from None


def _activity_workflow_id() -> str | None:
    try:
        return activity.info().workflow_id
    except RuntimeError:
        return None


def _log_activity_failure(
    context: dict[str, str | None], category: str, *, checks: str | None = None
) -> None:
    failure_context = {**context, "category": category, "checks": checks}
    LOGGER.warning(
        "Deployment activity failed workflow_id=%s device_name=%s activity=%s "
        "target=%s checks=%s category=%s",
        context.get("workflow_id"),
        context.get("device_name"),
        context.get("activity"),
        context.get("target"),
        checks,
        category,
        extra=failure_context,
    )


@activity.defn(name="prepare_device_deployment")
def prepare_device_deployment(request: DeployDeviceConfigRequest) -> PreparedDeployment:
    _contain_temporal_activity_logging()
    context = {
        "event_type": "network.deployment.requested",
        "event_id": str(request.event_id),
        "correlation_id": str(request.correlation_id),
        "workflow_id": deployment_workflow_id_for(request.event_id),
        "device_name": request.device_name,
        "activity": "prepare_device_deployment",
    }
    LOGGER.info(
        "Preparing device deployment event_type=%s event_id=%s correlation_id=%s "
        "workflow_id=%s device_name=%s activity=%s",
        context["event_type"],
        context["event_id"],
        context["correlation_id"],
        context["workflow_id"],
        context["device_name"],
        context["activity"],
        extra=context,
    )

    try:
        settings, _, _ = _settings()
        with NautobotClient(
            str(settings.nautobot_url),
            settings.nautobot_token.get_secret_value(),
            timeout=settings.probe_timeout_seconds,
        ) as client:
            snapshot = client.get_deployment_intent(request.device_name)

        intent = snapshot.intent
        if intent.name != request.device_name:
            raise ApplicationError(
                "Nautobot intent does not match the requested device",
                type="intent_invalid",
                non_retryable=True,
            )
        if intent.platform != "nokia_srl":
            raise ApplicationError(
                "device platform is unsupported",
                type="unsupported_platform",
                non_retryable=True,
            )

        write_result = _write_srlinux_artifact(intent, ARTIFACT_DIRECTORY)
        expected_path = ARTIFACT_DIRECTORY / f"{request.device_name}.cfg"
        if write_result.path != expected_path:
            raise ApplicationError(
                "artifact path does not match the requested device",
                type="artifact_mismatch",
                non_retryable=True,
            )
        if not 1 <= write_result.byte_count <= MAX_ARTIFACT_BYTES:
            raise ApplicationError(
                "artifact shape is invalid",
                type="artifact_invalid",
                non_retryable=True,
            )
        artifact = ArtifactIdentity(
            device_name=request.device_name,
            artifact_path=write_result.path.as_posix(),
            sha256=write_result.sha256,
            byte_count=write_result.byte_count,
        )
        _verify_artifact_shape(write_result.path, request.device_name, artifact)

        target = DeploymentTarget(
            device_name=request.device_name,
            management_address=snapshot.management_address,
            platform="nokia_srl",
            gnmi_port=settings.device_gnmi_port,
            tls_mode=settings.device_gnmi_tls_mode,
        )
        expected_state = expected_state_from_intent(intent)
        result = PreparedDeployment(
            artifact=artifact,
            target=target,
            expected_state=expected_state,
        )
    except ApplicationError as exc:
        _log_activity_failure(context, exc.type or "internal_error")
        raise
    except Exception as exc:
        classification = _prepare_classification(exc)
        _log_activity_failure(context, classification[0])
        _raise_classified(*classification)
    LOGGER.info(
        "Prepared device deployment device_name=%s target=%s artifact_sha256=%s",
        request.device_name,
        target.management_address,
        artifact.sha256,
        extra={
            **context,
            "target": str(target.management_address),
            "artifact_sha256": artifact.sha256,
        },
    )
    return result


@activity.defn(name="deploy_device_artifact")
def deploy_device_artifact(prepared: PreparedDeployment) -> DeploymentResult:
    _contain_temporal_activity_logging()
    context = {
        "workflow_id": _activity_workflow_id(),
        "activity": "deploy_device_artifact",
        "device_name": prepared.target.device_name,
        "target": str(prepared.target.management_address),
    }
    try:
        settings, username, password = _settings()
        client = _client(settings, username, password)
        LOGGER.info(
            "Deploying device artifact workflow_id=%s device_name=%s activity=%s "
            "target=%s artifact_sha256=%s",
            context["workflow_id"],
            context["device_name"],
            context["activity"],
            context["target"],
            prepared.artifact.sha256,
            extra={**context, "artifact_sha256": prepared.artifact.sha256},
        )
        result = client.deploy(prepared)
    except ApplicationError as exc:
        _log_activity_failure(context, exc.type or "internal_error")
        raise
    except Exception as exc:
        classification = _device_classification(exc, validating=False)
        _log_activity_failure(context, classification[0])
        _raise_classified(*classification)
    return result


def validation_result(
    prepared: PreparedDeployment,
    observed_state: dict[str, str | int | bool | None],
) -> DeviceValidationResult:
    result = compare_device_state(prepared, observed_state)
    expected = prepared.expected_state
    LOGGER.info(
        "Validated device state workflow_id=%s device_name=%s activity=%s target=%s "
        "status=%s checks=%s",
        _activity_workflow_id(),
        expected.device_name,
        "validate_device_state",
        prepared.target.management_address,
        result.status,
        ",".join(check.name for check in result.checks),
        extra={
            "workflow_id": _activity_workflow_id(),
            "activity": "validate_device_state",
            "device_name": expected.device_name,
            "target": str(prepared.target.management_address),
            "validation_status": result.status,
            "checks": ",".join(check.name for check in result.checks),
        },
    )
    return result


@activity.defn(name="validate_device_state")
def validate_device_state(prepared: PreparedDeployment) -> DeviceValidationResult:
    _contain_temporal_activity_logging()
    context = {
        "workflow_id": _activity_workflow_id(),
        "activity": "validate_device_state",
        "device_name": prepared.target.device_name,
        "target": str(prepared.target.management_address),
    }
    try:
        settings, username, password = _settings()
        observed_state = _client(settings, username, password).read_native_state(prepared)
        result = validation_result(prepared, observed_state)
    except ApplicationError as exc:
        _log_activity_failure(context, exc.type or "internal_error")
        raise
    except Exception as exc:
        classification = _device_classification(exc, validating=True)
        _log_activity_failure(context, classification[0])
        _raise_classified(*classification)

    if result.status == "failed":
        failed = tuple(check for check in result.checks if check.status == "failed")
        convergence_suffixes = (".oper_state", ".status", ".session_state")
        retryable = all(
            check.observed is None or check.name.endswith(convergence_suffixes)
            for check in failed
        )
        category = "validation_not_converged" if retryable else "validation_failed"
        _log_activity_failure(
            context,
            category,
            checks=",".join(check.name for check in failed),
        )
        if retryable:
            _raise_classified(
                "validation_not_converged",
                "device state has not converged",
                False,
            )
        _raise_classified(
            "validation_failed",
            "device state did not match intended invariants",
            True,
        )
    return result


__all__ = [
    "deploy_device_artifact",
    "expected_state_from_intent",
    "prepare_device_deployment",
    "validation_result",
    "validate_device_state",
]

# Retained for the accepted Feature 004 unit boundary.
_validation_result = validation_result
