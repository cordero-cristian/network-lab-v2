import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from network_automation.events.models import (
    DeploymentCompleted,
    DeploymentFailed,
    DeploymentRequested,
)
from network_automation.events import producer as producer_module


REQUEST_JSON = (
    b'{"event_type":"network.deployment.requested","event_version":1,'
    b'"event_id":"08660568-3d4c-4901-9a77-8a4fb0e68072",'
    b'"correlation_id":"eaf41a9d-9cb8-4de0-bd68-32bbc47e5030",'
    b'"device_name":"f004-leaf01","requested_at":"2026-09-10T18:00:00Z",'
    b'"source":"cli"}'
)
COMPLETED_JSON = (
    b'{"event_type":"network.deployment.completed","event_version":1,'
    b'"event_id":"577e85e8-f2ed-4c28-80ca-20d6e78c9df8",'
    b'"correlation_id":"eaf41a9d-9cb8-4de0-bd68-32bbc47e5030",'
    b'"device_name":"f004-leaf01",'
    b'"workflow_id":"deploy-device-config:08660568-3d4c-4901-9a77-8a4fb0e68072",'
    b'"artifact_path":"artifacts/configs/f004-leaf01.cfg",'
    b'"artifact_sha256":"cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887",'
    b'"artifact_bytes":1248,"deployed_at":"2026-09-10T18:00:04Z",'
    b'"validation_status":"passed","completed_at":"2026-09-10T18:00:12Z"}'
)
FAILED_JSON = (
    b'{"event_type":"network.deployment.failed","event_version":1,'
    b'"event_id":"06a31ce0-d0e3-41fd-9079-2d52b26f23c3",'
    b'"correlation_id":"eaf41a9d-9cb8-4de0-bd68-32bbc47e5030",'
    b'"device_name":"f004-leaf01",'
    b'"workflow_id":"deploy-device-config:08660568-3d4c-4901-9a77-8a4fb0e68072",'
    b'"failure_stage":"validate","error_type":"validation_failed",'
    b'"error_message":"device state did not match intended invariants",'
    b'"failed_at":"2026-09-10T18:01:34Z",'
    b'"artifact_sha256":"cf3dbb569d2083452c9d9ccf13d5e72668bcf059cba7c27a10e7c7c3b5cf7887",'
    b'"artifact_bytes":1248,"deployed_at":"2026-09-10T18:00:04Z"}'
)


def data(payload: bytes) -> dict[str, object]:
    return json.loads(payload)


def test_deployment_event_examples_decode_and_encode_exactly() -> None:
    for model, payload in (
        (DeploymentRequested, REQUEST_JSON),
        (DeploymentCompleted, COMPLETED_JSON),
        (DeploymentFailed, FAILED_JSON),
    ):
        event = model.model_validate_json(payload)
        assert event.model_dump_json().encode() == payload


def test_deployment_events_are_frozen_and_reject_unknown_fields() -> None:
    event = DeploymentRequested.model_validate_json(REQUEST_JSON)
    with pytest.raises(ValidationError):
        event.device_name = "f004-spine01"  # type: ignore[misc]

    for model, payload in (
        (DeploymentRequested, REQUEST_JSON),
        (DeploymentCompleted, COMPLETED_JSON),
        (DeploymentFailed, FAILED_JSON),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(data(payload) | {"password": "super-secret"})


def test_each_event_rejects_wrong_type_version_uuid_device_and_time() -> None:
    cases = (
        (DeploymentRequested, REQUEST_JSON, "requested_at"),
        (DeploymentCompleted, COMPLETED_JSON, "completed_at"),
        (DeploymentFailed, FAILED_JSON, "failed_at"),
    )
    for model, payload, time_field in cases:
        for change in (
            {"event_type": "network.deployment.unknown"},
            {"event_version": 2},
            {"event_version": "1"},
            {"event_id": "not-a-uuid"},
            {"device_name": "../f004-leaf01"},
            {time_field: "2026-09-10T19:00:00+01:00"},
        ):
            with pytest.raises(ValidationError):
                model.model_validate(data(payload) | change)


def test_request_source_and_completion_identity_have_safe_exact_bounds() -> None:
    for change in ({"source": ""}, {"source": "x" * 65}, {"source": 1}):
        with pytest.raises(ValidationError):
            DeploymentRequested.model_validate(data(REQUEST_JSON) | change)

    for change in (
        {"workflow_id": "render-device-config:08660568-3d4c-4901-9a77-8a4fb0e68072"},
        {"artifact_path": "artifacts/configs/f004-spine01.cfg"},
        {"artifact_sha256": "A" * 64},
        {"artifact_bytes": 0},
        {"artifact_bytes": 1024 * 1024 + 1},
        {"validation_status": "failed"},
    ):
        with pytest.raises(ValidationError):
            DeploymentCompleted.model_validate(data(COMPLETED_JSON) | change)


def test_failure_categories_and_metadata_depend_on_failure_stage() -> None:
    prepare = data(FAILED_JSON) | {
        "failure_stage": "prepare",
        "error_type": "intent_invalid",
        "artifact_sha256": None,
        "artifact_bytes": None,
        "deployed_at": None,
    }
    deploy = data(FAILED_JSON) | {
        "failure_stage": "deploy",
        "error_type": "device_unavailable",
        "deployed_at": None,
    }
    assert DeploymentFailed.model_validate(prepare)
    assert DeploymentFailed.model_validate(deploy)
    assert DeploymentFailed.model_validate_json(FAILED_JSON)

    invalid = (
        prepare | {"artifact_sha256": "0" * 64},
        deploy | {"artifact_bytes": None},
        deploy | {"deployed_at": "2026-09-10T18:00:04Z"},
        data(FAILED_JSON) | {"deployed_at": None},
        prepare | {"error_type": "configuration_rejected"},
        deploy | {"error_type": "validation_failed"},
        data(FAILED_JSON) | {"error_type": "intent_invalid"},
        data(FAILED_JSON) | {"failure_stage": "publish"},
    )
    for values in invalid:
        with pytest.raises(ValidationError):
            DeploymentFailed.model_validate(values)


def test_failure_message_is_bounded_and_payload_has_no_unsafe_fields() -> None:
    for message in ("", "x" * 257, "line one\nraw configuration"):
        with pytest.raises(ValidationError):
            DeploymentFailed.model_validate(data(FAILED_JSON) | {"error_message": message})

    event = DeploymentFailed.model_validate_json(FAILED_JSON)
    assert set(event.model_dump()) == {
        "event_type",
        "event_version",
        "event_id",
        "correlation_id",
        "device_name",
        "workflow_id",
        "failure_stage",
        "error_type",
        "error_message",
        "failed_at",
        "artifact_sha256",
        "artifact_bytes",
        "deployed_at",
    }
    serialized = event.model_dump_json()
    for forbidden in ("password", "management_address", "artifact_content", "traceback"):
        assert forbidden not in serialized


def test_all_deployment_event_payloads_have_only_safe_contract_context() -> None:
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
            "artifact_sha256",
            "artifact_bytes",
            "deployed_at",
            "validation_status",
            "completed_at",
        },
        {
            "event_type",
            "event_version",
            "event_id",
            "correlation_id",
            "device_name",
            "workflow_id",
            "failure_stage",
            "error_type",
            "error_message",
            "failed_at",
            "artifact_sha256",
            "artifact_bytes",
            "deployed_at",
        },
    )
    for model, payload, fields in zip(
        (DeploymentRequested, DeploymentCompleted, DeploymentFailed),
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


def test_deployment_event_utc_values_serialize_with_z() -> None:
    values = data(REQUEST_JSON)
    values["requested_at"] = datetime(2026, 9, 10, 18, tzinfo=timezone.utc)
    event = DeploymentRequested.model_validate(values)
    assert event.model_dump(mode="json")["requested_at"] == "2026-09-10T18:00:00Z"
    assert isinstance(event.event_id, UUID)


def test_producer_additively_maps_deployment_models_to_exact_topics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict[str, object]] = []

    class FakeProducer:
        def __init__(self, config: dict[str, object]) -> None:
            assert config == {"bootstrap.servers": "kafka.test:9092"}

        def produce(
            self, topic: str, *, key: str, value: bytes, callback: object
        ) -> None:
            records.append({"topic": topic, "key": key, "value": value})
            callback(None, object())  # type: ignore[operator]

        def flush(self, timeout: float) -> int:
            assert timeout == 7
            return 0

    monkeypatch.setattr(producer_module, "Producer", FakeProducer)
    settings = SimpleNamespace(
        kafka_bootstrap_servers="kafka.test:9092",
        deployment_request_topic="deployment-requests.test",
        deployment_completed_topic="deployment-completed.test",
        deployment_failed_topic="deployment-failed.test",
        probe_timeout_seconds=7,
    )
    events = (
        DeploymentRequested.model_validate_json(REQUEST_JSON),
        DeploymentCompleted.model_validate_json(COMPLETED_JSON),
        DeploymentFailed.model_validate_json(FAILED_JSON),
    )

    for event in events:
        producer_module.publish_event(event, settings)  # type: ignore[arg-type]

    assert [record["topic"] for record in records] == [
        "deployment-requests.test",
        "deployment-completed.test",
        "deployment-failed.test",
    ]
    for event, record in zip(events, records, strict=True):
        assert record["key"] == str(event.event_id)
        assert record["value"] == event.model_dump_json().encode("utf-8")


def test_existing_render_event_serialization_is_unchanged() -> None:
    from network_automation.events.models import RenderRequested

    payload = (
        b'{"event_type":"network.render.requested","event_version":1,'
        b'"event_id":"77ee1844-cd3a-4c45-8de7-3dd76fc7da2d",'
        b'"correlation_id":"fb2b2b84-a0e2-45c1-a870-59c636c34a80",'
        b'"device_name":"leaf01","requested_at":"2026-09-09T18:00:00Z",'
        b'"source":"cli"}'
    )
    assert RenderRequested.model_validate_json(payload).model_dump_json().encode() == payload
