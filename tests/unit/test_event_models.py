import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from network_automation.events.models import (
    ArtifactMetadata,
    RenderCompleted,
    RenderDeviceConfigRequest,
    RenderFailed,
    RenderRequested,
    workflow_id_for,
)


REQUEST_JSON = (
    b'{"event_type":"network.render.requested","event_version":1,'
    b'"event_id":"77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",'
    b'"correlation_id":"fb2b2b84-a0e2-45c1-a870-59c636c34a80",'
    b'"device_name":"leaf01","requested_at":"2026-09-09T18:00:00Z","source":"cli"}'
)
COMPLETED_JSON = (
    b'{"event_type":"network.render.completed","event_version":1,'
    b'"event_id":"895c05a7-8486-48b1-9a7b-0bce533a92b8",'
    b'"correlation_id":"fb2b2b84-a0e2-45c1-a870-59c636c34a80",'
    b'"device_name":"leaf01",'
    b'"workflow_id":"render-device-config:77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",'
    b'"artifact_path":"artifacts/configs/leaf01.cfg",'
    b'"completed_at":"2026-09-09T18:00:03Z"}'
)
FAILED_JSON = (
    b'{"event_type":"network.render.failed","event_version":1,'
    b'"event_id":"dd26263d-4701-47be-943c-8b843f9e7881",'
    b'"correlation_id":"fb2b2b84-a0e2-45c1-a870-59c636c34a80",'
    b'"device_name":"leaf01",'
    b'"workflow_id":"render-device-config:77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",'
    b'"error_type":"intent_invalid",'
    b'"error_message":"device intent validation failed",'
    b'"failed_at":"2026-09-09T18:00:03Z"}'
)


def request_data() -> dict[str, object]:
    return json.loads(REQUEST_JSON)


def completed_data() -> dict[str, object]:
    return json.loads(COMPLETED_JSON)


def failed_data() -> dict[str, object]:
    return json.loads(FAILED_JSON)


def test_contract_examples_decode_and_encode_exactly() -> None:
    cases = (
        (RenderRequested, REQUEST_JSON),
        (RenderCompleted, COMPLETED_JSON),
        (RenderFailed, FAILED_JSON),
    )

    for model, payload in cases:
        event = model.model_validate_json(payload)
        assert event.model_dump_json().encode() == payload
        assert event.model_dump_json().encode() == payload


def test_all_render_event_payloads_have_only_safe_contract_context() -> None:
    expected_fields = (
        {
            "event_type",
            "event_version",
            "event_id",
            "correlation_id",
            "device_name",
            "requested_at",
            "source",
        },
        {
            "event_type",
            "event_version",
            "event_id",
            "correlation_id",
            "device_name",
            "workflow_id",
            "artifact_path",
            "completed_at",
        },
        {
            "event_type",
            "event_version",
            "event_id",
            "correlation_id",
            "device_name",
            "workflow_id",
            "error_type",
            "error_message",
            "failed_at",
        },
    )
    for model, payload, fields in zip(
        (RenderRequested, RenderCompleted, RenderFailed),
        (REQUEST_JSON, COMPLETED_JSON, FAILED_JSON),
        expected_fields,
        strict=True,
    ):
        event = model.model_validate_json(payload)
        serialized = event.model_dump_json()
        assert set(event.model_dump()) == fields
        for forbidden in (
            "password",
            "credential",
            "management_address",
            "artifact_content",
            "raw_response",
            "traceback",
            "stack",
            "set / ",
        ):
            assert forbidden not in serialized.lower()


def test_event_models_are_frozen_and_reject_unknown_fields() -> None:
    event = RenderRequested.model_validate_json(REQUEST_JSON)

    with pytest.raises(ValidationError):
        event.device_name = "leaf02"  # type: ignore[misc]
    for model, data in (
        (RenderRequested, request_data()),
        (RenderCompleted, completed_data()),
        (RenderFailed, failed_data()),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(data | {"unexpected": True})


def test_request_rejects_wrong_contract_values_and_unsafe_inputs() -> None:
    invalid = (
        {"event_type": "network.render.completed"},
        {"event_version": 2},
        {"event_version": "1"},
        {"event_id": "not-a-uuid"},
        {"device_name": "../leaf01"},
        {"requested_at": "2026-09-09T19:00:00+01:00"},
        {"requested_at": "2026-09-09T18:00:00"},
        {"source": ""},
        {"source": "x" * 65},
        {"source": 1},
    )

    for change in invalid:
        with pytest.raises(ValidationError):
            RenderRequested.model_validate(request_data() | change)
    for required_field in ("event_type", "event_version"):
        data = request_data()
        data.pop(required_field)
        with pytest.raises(ValidationError):
            RenderRequested.model_validate(data)


def test_utc_values_serialize_with_z() -> None:
    data = request_data()
    data["requested_at"] = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)

    event = RenderRequested.model_validate(data)

    assert event.model_dump(mode="json")["requested_at"] == "2026-09-09T18:00:00Z"
    data["requested_at"] = datetime(
        2026, 9, 9, 19, tzinfo=timezone(timedelta(hours=1))
    )
    with pytest.raises(ValidationError):
        RenderRequested.model_validate(data)


def test_each_event_rejects_its_wrong_type_version_and_non_utc_time() -> None:
    cases = (
        (RenderRequested, request_data(), "requested_at"),
        (RenderCompleted, completed_data(), "completed_at"),
        (RenderFailed, failed_data(), "failed_at"),
    )

    for model, data, time_field in cases:
        for change in (
            {"event_type": "network.render.unknown"},
            {"event_version": 2},
            {time_field: "2026-09-09T19:00:00+01:00"},
        ):
            with pytest.raises(ValidationError):
                model.model_validate(data | change)


def test_completion_requires_its_device_artifact_path() -> None:
    event = RenderCompleted.model_validate_json(COMPLETED_JSON)
    assert event.artifact_path == "artifacts/configs/leaf01.cfg"

    with pytest.raises(ValidationError):
        RenderCompleted.model_validate(
            completed_data() | {"artifact_path": "artifacts/configs/leaf02.cfg"}
        )


def test_failure_accepts_only_documented_safe_categories_and_text_bounds() -> None:
    categories = {
        "nautobot_unavailable",
        "artifact_unavailable",
        "intent_invalid",
        "nautobot_rejected",
        "unsupported_platform",
        "render_invalid",
        "internal_error",
    }
    for category in categories:
        assert RenderFailed.model_validate(failed_data() | {"error_type": category})

    for change in (
        {"error_type": "unknown"},
        {"error_message": ""},
        {"error_message": "x" * 257},
        {"workflow_id": ""},
        {"workflow_id": "x" * 129},
        {"failed_at": "2026-09-09T19:00:03+01:00"},
    ):
        with pytest.raises(ValidationError):
            RenderFailed.model_validate(failed_data() | change)


def test_workflow_input_metadata_and_identity_are_minimal_and_strict() -> None:
    event_id = UUID("77ee1844-cd3a-4c45-8de7-3dd76fc7da2d")
    workflow_input = RenderDeviceConfigRequest(
        event_id=event_id,
        correlation_id=UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80"),
        device_name="leaf01",
    )
    metadata = ArtifactMetadata(
        device_name="leaf01", artifact_path="artifacts/configs/leaf01.cfg"
    )

    assert workflow_id_for(event_id) == f"render-device-config:{event_id}"
    assert set(workflow_input.model_dump()) == {"event_id", "correlation_id", "device_name"}
    assert RenderDeviceConfigRequest.model_validate_json(
        workflow_input.model_dump_json()
    ) == workflow_input
    assert ArtifactMetadata.model_validate_json(metadata.model_dump_json()) == metadata
    assert metadata.artifact_path == "artifacts/configs/leaf01.cfg"
    with pytest.raises(ValidationError):
        RenderDeviceConfigRequest.model_validate(workflow_input.model_dump() | {"source": "cli"})
    with pytest.raises(ValidationError):
        ArtifactMetadata(device_name="leaf01", artifact_path="other.cfg")
