import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from network_automation.events import producer as event_producer
from network_automation.events.models import RenderCompleted, RenderFailed, RenderRequested
from network_automation.events.producer import EventPublishError, publish_event


EVENT_ID = UUID("77ee1844-cd3a-4c45-8de7-3dd76fc7da2d")
CORRELATION_ID = UUID("fb2b2b84-a0e2-45c1-a870-59c636c34a80")
NOW = datetime(2026, 9, 9, 18, tzinfo=timezone.utc)


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        kafka_bootstrap_servers="kafka.test:9092",
        render_request_topic="requests.test",
        render_completed_topic="completed.test",
        render_failed_topic="failed.test",
        probe_timeout_seconds=7,
    )


def events() -> tuple[RenderRequested, RenderCompleted, RenderFailed]:
    common = {"correlation_id": CORRELATION_ID, "device_name": "leaf01"}
    return (
        RenderRequested(
            event_type="network.render.requested",
            event_version=1,
            event_id=EVENT_ID,
            requested_at=NOW,
            source="cli",
            **common,
        ),
        RenderCompleted(
            event_type="network.render.completed",
            event_version=1,
            event_id=UUID("895c05a7-8486-48b1-9a7b-0bce533a92b8"),
            workflow_id=f"render-device-config:{EVENT_ID}",
            artifact_path="artifacts/configs/leaf01.cfg",
            completed_at=NOW,
            **common,
        ),
        RenderFailed(
            event_type="network.render.failed",
            event_version=1,
            event_id=UUID("dd26263d-4701-47be-943c-8b843f9e7881"),
            workflow_id=f"render-device-config:{EVENT_ID}",
            error_type="intent_invalid",
            error_message="device intent validation failed",
            failed_at=NOW,
            **common,
        ),
    )


class FakeProducer:
    instances: list["FakeProducer"] = []
    delivery_error: object | None = None
    remaining = 0

    def __init__(self, config: dict[str, object]) -> None:
        self.config = config
        self.records: list[dict[str, object]] = []
        self.flush_timeout: float | None = None
        self.__class__.instances.append(self)

    def produce(self, topic: str, *, key: str, value: bytes, callback) -> None:
        self.records.append({"topic": topic, "key": key, "value": value})
        callback(self.delivery_error, object())

    def flush(self, timeout: float) -> int:
        self.flush_timeout = timeout
        return self.remaining


@pytest.fixture(autouse=True)
def fake_producer(monkeypatch: pytest.MonkeyPatch):
    FakeProducer.instances.clear()
    FakeProducer.delivery_error = None
    FakeProducer.remaining = 0
    monkeypatch.setattr(event_producer, "Producer", FakeProducer)


def test_publish_maps_each_event_to_topic_key_and_json() -> None:
    expected_topics = ("requests.test", "completed.test", "failed.test")

    for event, topic in zip(events(), expected_topics, strict=True):
        publish_event(event, settings())
        producer = FakeProducer.instances[-1]
        record = producer.records[0]
        assert producer.config["bootstrap.servers"] == "kafka.test:9092"
        assert record["topic"] == topic
        assert record["key"] == str(event.event_id)
        assert record["value"] == event.model_dump_json().encode("utf-8")
        assert json.loads(record["value"])["event_type"] == event.event_type
        assert producer.flush_timeout == 7


def test_repeated_publication_uses_stable_bytes() -> None:
    event = events()[1]

    publish_event(event, settings())
    publish_event(event, settings())

    assert FakeProducer.instances[0].records[0]["value"] == (
        FakeProducer.instances[1].records[0]["value"]
    )


def test_delivery_error_is_wrapped_without_leaking_details() -> None:
    FakeProducer.delivery_error = RuntimeError("broker exposed super-secret")

    with pytest.raises(EventPublishError) as error:
        publish_event(events()[0], settings())

    assert "super-secret" not in str(error.value)
    assert error.value.__cause__ is None


def test_delivery_timeout_is_a_safe_publish_error() -> None:
    FakeProducer.remaining = 1

    with pytest.raises(EventPublishError) as error:
        publish_event(events()[0], settings())

    assert "super-secret" not in str(error.value)
    assert "timeout" in str(error.value).lower()
