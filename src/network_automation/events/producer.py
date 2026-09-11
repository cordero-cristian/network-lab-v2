"""Narrow Kafka publisher for the render and deployment event contracts."""

from __future__ import annotations

from confluent_kafka import Producer

from network_automation.events.models import (
    DeploymentCompleted,
    DeploymentFailed,
    DeploymentRequested,
    RenderCompleted,
    RenderFailed,
    RenderRequested,
)
from network_automation.settings import LabSettings

AutomationEvent = (
    RenderRequested
    | RenderCompleted
    | RenderFailed
    | DeploymentRequested
    | DeploymentCompleted
    | DeploymentFailed
)


class EventPublishError(RuntimeError):
    """A credential-safe Kafka publication failure."""


def publish_event(event: AutomationEvent, settings: LabSettings | None = None) -> None:
    settings = settings or LabSettings()
    if isinstance(event, RenderRequested):
        topic = settings.render_request_topic
    elif isinstance(event, RenderCompleted):
        topic = settings.render_completed_topic
    elif isinstance(event, RenderFailed):
        topic = settings.render_failed_topic
    elif isinstance(event, DeploymentRequested):
        topic = settings.deployment_request_topic
    elif isinstance(event, DeploymentCompleted):
        topic = settings.deployment_completed_topic
    elif isinstance(event, DeploymentFailed):
        topic = settings.deployment_failed_topic
    else:
        raise TypeError("unsupported automation event type")

    delivery_errors: list[object] = []

    def delivered(error: object, _message: object) -> None:
        if error is not None:
            delivery_errors.append(error)

    producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    try:
        producer.produce(
            topic,
            key=str(event.event_id),
            value=event.model_dump_json().encode("utf-8"),
            callback=delivered,
        )
        remaining = producer.flush(settings.probe_timeout_seconds)
    except Exception as exc:
        raise EventPublishError("event publication failed") from None
    if remaining:
        raise EventPublishError("event publication timeout")
    if delivery_errors:
        raise EventPublishError("event delivery failed")
