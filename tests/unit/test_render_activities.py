from __future__ import annotations

from pathlib import Path
from uuid import UUID

import httpx
import pytest
from jinja2 import TemplateError
from pydantic import ValidationError
from temporalio.exceptions import ApplicationError

from network_automation.activities import rendering
from network_automation.events.models import RenderCompleted, RenderDeviceConfigRequest
from network_automation.intent.models import InterfaceIntent
from network_automation.intent.nautobot import NautobotError
from network_automation.rendering.srlinux import UnsupportedPlatformError


def request() -> RenderDeviceConfigRequest:
    return RenderDeviceConfigRequest(
        event_id=UUID("77ee1844-cd3a-4c45-8de7-3dd76fc7da2d"),
        correlation_id=UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80"),
        device_name="leaf01",
    )


def test_render_activity_delegates_complete_feature_002_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Path]] = []

    def render_device(name: str, output_dir: Path) -> Path:
        calls.append((name, output_dir))
        return output_dir / f"{name}.cfg"

    monkeypatch.setattr(rendering, "render_device", render_device)

    result = rendering.render_device_artifact(request())

    assert calls == [("leaf01", Path("artifacts/configs"))]
    assert result.device_name == "leaf01"
    assert result.artifact_path == "artifacts/configs/leaf01.cfg"
    assert set(result.model_dump()) == {"device_name", "artifact_path"}


def test_render_activity_can_safely_repeat_an_uncertain_completed_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def render_device(name: str, output_dir: Path) -> Path:
        nonlocal calls
        calls += 1
        return output_dir / f"{name}.cfg"

    monkeypatch.setattr(rendering, "render_device", render_device)

    first = rendering.render_device_artifact(request())
    second = rendering.render_device_artifact(request())

    assert calls == 2
    assert first == second


def test_publish_activity_delegates_exact_validated_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[object] = []
    result = RenderCompleted.model_validate_json(
        """{
          "event_type": "network.render.completed",
          "event_version": 1,
          "event_id": "895c05a7-8486-48b1-9a7b-0bce533a92b8",
          "correlation_id": "fb2b2b84-a0e2-45c1-a870-59c636c34a80",
          "device_name": "leaf01",
          "workflow_id": "render-device-config:77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",
          "artifact_path": "artifacts/configs/leaf01.cfg",
          "completed_at": "2026-09-09T18:00:03Z"
        }"""
    )

    def publish_event(value: object, *args: object, **kwargs: object) -> None:
        published.append(value)

    monkeypatch.setattr(rendering, "publish_event", publish_event)

    assert rendering.publish_render_result(result) is None
    assert published == [result]


def test_publish_activity_preserves_safe_broker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = RenderCompleted.model_validate_json(
        """{
          "event_type": "network.render.completed",
          "event_version": 1,
          "event_id": "895c05a7-8486-48b1-9a7b-0bce533a92b8",
          "correlation_id": "fb2b2b84-a0e2-45c1-a870-59c636c34a80",
          "device_name": "leaf01",
          "workflow_id": "render-device-config:77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",
          "artifact_path": "artifacts/configs/leaf01.cfg",
          "completed_at": "2026-09-09T18:00:03Z"
        }"""
    )

    def fail(*_: object, **__: object) -> None:
        raise rendering.EventPublishError("result publication failed")

    monkeypatch.setattr(rendering, "publish_event", fail)

    with pytest.raises(rendering.EventPublishError, match="result publication failed"):
        rendering.publish_render_result(result)


def test_render_activity_classifies_retryable_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_request = httpx.Request("GET", "http://nautobot.test/api/dcim/devices/")
    unavailable_causes: list[Exception] = [
        httpx.ReadTimeout("credential=super-secret", request=http_request),
        httpx.ConnectError("credential=super-secret", request=http_request),
        httpx.ReadError("credential=super-secret", request=http_request),
        httpx.WriteError("credential=super-secret", request=http_request),
        httpx.RemoteProtocolError("credential=super-secret"),
    ]
    unavailable_causes.extend(
        httpx.HTTPStatusError(
            "credential=super-secret",
            request=http_request,
            response=httpx.Response(status, request=http_request),
        )
        for status in (408, 429, 500, 503)
    )

    cases: list[tuple[Exception, str]] = []
    for cause in unavailable_causes:
        error = NautobotError("Nautobot request failed safely")
        error.__cause__ = cause
        cases.append((error, "nautobot_unavailable"))
    cases.append((OSError("credential=super-secret"), "artifact_unavailable"))

    for source_error, expected_type in cases:
        def fail(*_: object, error: Exception = source_error) -> Path:
            raise error

        monkeypatch.setattr(rendering, "render_device", fail)
        with pytest.raises(ApplicationError) as raised:
            rendering.render_device_artifact(request())

        assert raised.value.type == expected_type
        assert raised.value.non_retryable is False
        assert "super-secret" not in raised.value.message


def test_render_activity_classifies_permanent_failures_without_raw_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        InterfaceIntent(name="ethernet-1/1", description="peer", ipv4="super-secret")
    except ValidationError as validation_error:
        invalid_intent = validation_error

    http_request = httpx.Request("GET", "http://nautobot.test/api/dcim/devices/")
    rejected_errors: list[NautobotError] = []
    for status in (400, 401, 403, 404):
        rejected = NautobotError("Nautobot request failed safely")
        rejected.__cause__ = httpx.HTTPStatusError(
            "authorization=super-secret",
            request=http_request,
            response=httpx.Response(status, request=http_request),
        )
        rejected_errors.append(rejected)
    cases = [
        (NautobotError("raw super-secret payload"), "intent_invalid"),
        (invalid_intent, "intent_invalid"),
        (UnsupportedPlatformError("super-secret platform"), "unsupported_platform"),
        (TemplateError("rendered super-secret configuration"), "render_invalid"),
        (RuntimeError("traceback super-secret"), "internal_error"),
    ]
    cases.extend((error, "nautobot_rejected") for error in rejected_errors)

    for source_error, expected_type in cases:
        def fail(*_: object, error: Exception = source_error) -> Path:
            raise error

        monkeypatch.setattr(rendering, "render_device", fail)
        with pytest.raises(ApplicationError) as raised:
            rendering.render_device_artifact(request())

        assert raised.value.type == expected_type
        assert raised.value.non_retryable is True
        assert raised.value.message
        assert "super-secret" not in raised.value.message
        assert "traceback" not in raised.value.message.lower()
