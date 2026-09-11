"""External render and result-publication activities."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from jinja2 import TemplateError
from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError

from network_automation.cli.render import render_device
from network_automation.events.models import (
    ArtifactMetadata,
    DeploymentCompleted,
    DeploymentFailed,
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
)
from network_automation.events.producer import EventPublishError, publish_event
from network_automation.intent.nautobot import NautobotError
from network_automation.rendering.srlinux import UnsupportedPlatformError

LOGGER = logging.getLogger(__name__)


def _classification(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, NautobotError):
        cause = exc.__cause__
        if isinstance(cause, httpx.TransportError):
            return "nautobot_unavailable", "Nautobot is temporarily unavailable", False
        if isinstance(cause, httpx.HTTPStatusError):
            if cause.response.status_code in {408, 429} or cause.response.status_code >= 500:
                return "nautobot_unavailable", "Nautobot is temporarily unavailable", False
            return "nautobot_rejected", "Nautobot rejected the request", True
        return "intent_invalid", "device intent validation failed", True
    if isinstance(exc, OSError):
        return "artifact_unavailable", "artifact storage is temporarily unavailable", False
    if isinstance(exc, ValidationError):
        return "intent_invalid", "device intent validation failed", True
    if isinstance(exc, UnsupportedPlatformError):
        return "unsupported_platform", "device platform is unsupported", True
    if isinstance(exc, TemplateError):
        return "render_invalid", "configuration rendering failed", True
    return "internal_error", "rendering failed unexpectedly", True


@activity.defn(name="render_device_artifact")
def render_device_artifact(request: RenderDeviceConfigRequest) -> ArtifactMetadata:
    context = {
        "event_id": str(request.event_id),
        "correlation_id": str(request.correlation_id),
        "device_name": request.device_name,
        "activity": "render_device_artifact",
    }
    LOGGER.info(
        "Rendering requested artifact event_id=%s correlation_id=%s device_name=%s",
        context["event_id"],
        context["correlation_id"],
        context["device_name"],
        extra=context,
    )
    try:
        path = render_device(request.device_name, Path("artifacts/configs"))
    except Exception as exc:
        error_type, message, non_retryable = _classification(exc)
        raise ApplicationError(
            message,
            type=error_type,
            non_retryable=non_retryable,
        ) from None
    result = ArtifactMetadata(device_name=request.device_name, artifact_path=path.as_posix())
    LOGGER.info(
        "Rendered requested artifact event_id=%s correlation_id=%s device_name=%s",
        context["event_id"],
        context["correlation_id"],
        context["device_name"],
        extra=context,
    )
    return result


@activity.defn(name="publish_render_result")
def publish_render_result(
    result: RenderCompleted | RenderFailed | DeploymentCompleted | DeploymentFailed,
) -> None:
    category = getattr(result, "error_type", None)
    LOGGER.info(
        "Publishing automation result event_type=%s event_id=%s correlation_id=%s "
        "workflow_id=%s device_name=%s activity=publish_render_result category=%s",
        result.event_type,
        result.event_id,
        result.correlation_id,
        result.workflow_id,
        result.device_name,
        category,
        extra={
            "event_type": result.event_type,
            "event_id": str(result.event_id),
            "correlation_id": str(result.correlation_id),
            "workflow_id": result.workflow_id,
            "device_name": result.device_name,
            "activity": "publish_render_result",
            "category": category,
        },
    )
    publish_event(result)


__all__ = [
    "EventPublishError",
    "publish_render_result",
    "render_device_artifact",
]
