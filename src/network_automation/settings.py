"""Validated configuration at the local lab boundary."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

HOST_PORT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+:[0-9]{1,5}$")
COMPOSE_PROJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
RESOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_host_port(value: str) -> str:
    value = value.strip()
    if not HOST_PORT_PATTERN.fullmatch(value):
        raise ValueError("must use host:port syntax")
    port = int(value.rsplit(":", 1)[1])
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return value


class LabSettings(BaseSettings):
    """Connection settings used by host-side checks and integration tests."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LAB_",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    nautobot_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_ui_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8080")
    kafka_host_port: int = Field(default=9092, ge=1, le=65535)
    kafka_bootstrap_servers: str | None = None
    nautobot_username: str = Field(
        default="admin",
        validation_alias=AliasChoices("NAUTOBOT_SUPERUSER_NAME", "LAB_NAUTOBOT_USERNAME"),
    )
    nautobot_password: SecretStr = Field(
        validation_alias=AliasChoices(
            "NAUTOBOT_SUPERUSER_PASSWORD", "LAB_NAUTOBOT_PASSWORD"
        )
    )
    nautobot_token: SecretStr = Field(
        validation_alias=AliasChoices(
            "NAUTOBOT_SUPERUSER_API_TOKEN", "LAB_NAUTOBOT_TOKEN"
        )
    )
    probe_timeout_seconds: int = Field(default=10, ge=1, le=10)
    compose_project: str = "network-lab"
    render_request_topic: str = "network.render.requested"
    render_completed_topic: str = "network.render.completed"
    render_failed_topic: str = "network.render.failed"
    deployment_request_topic: str = "network.deployment.requested"
    deployment_completed_topic: str = "network.deployment.completed"
    deployment_failed_topic: str = "network.deployment.failed"
    render_consumer_group: str = "network-automation-render-consumer"
    temporal_task_queue: str = "network-automation"
    device_username: str | None = None
    device_password: SecretStr | None = None
    device_gnmi_port: int = Field(default=57401, ge=1, le=65535)
    device_gnmi_timeout_seconds: int = Field(default=10, ge=1, le=10)
    device_gnmi_tls_mode: Literal["insecure"] = "insecure"
    api_probe_timeout_seconds: int = Field(default=3, ge=1, le=10)
    api_overview_timeout_seconds: int = Field(default=8, ge=1, le=15)
    api_live_timeout_seconds: int = Field(default=15, ge=1, le=15)
    api_workflow_limit: int = Field(default=25, ge=1, le=50)
    api_workflow_hydration_concurrency: int = Field(default=4, ge=1, le=4)
    api_overview_workflow_limit: int = Field(default=8, ge=1, le=8)
    api_device_limit: int = Field(default=50, ge=1, le=100)
    api_artifact_root: Path = Path("artifacts")

    @field_validator("temporal_address")
    @classmethod
    def validate_temporal_address(cls, value: str) -> str:
        return _validate_host_port(value)

    @field_validator("temporal_namespace", "nautobot_username")
    @classmethod
    def validate_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("device_username")
    @classmethod
    def validate_optional_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("device_password")
    @classmethod
    def validate_optional_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value():
            raise ValueError("must not be empty")
        return value

    @field_validator("compose_project")
    @classmethod
    def validate_compose_project(cls, value: str) -> str:
        if not COMPOSE_PROJECT_PATTERN.fullmatch(value):
            raise ValueError("must be a lowercase Compose project name")
        return value

    @field_validator(
        "render_request_topic",
        "render_completed_topic",
        "render_failed_topic",
        "deployment_request_topic",
        "deployment_completed_topic",
        "deployment_failed_topic",
        "render_consumer_group",
        "temporal_task_queue",
    )
    @classmethod
    def validate_resource_name(cls, value: str) -> str:
        value = value.strip()
        if not RESOURCE_NAME_PATTERN.fullmatch(value):
            raise ValueError("must be a non-empty Kafka/task-queue-safe name")
        return value

    @model_validator(mode="after")
    def derive_and_validate_kafka_servers(self) -> LabSettings:
        if self.kafka_bootstrap_servers is None:
            self.kafka_bootstrap_servers = f"localhost:{self.kafka_host_port}"
        else:
            self.kafka_bootstrap_servers = ",".join(
                _validate_host_port(server)
                for server in self.kafka_bootstrap_servers.split(",")
            )
        topics = {
            self.render_request_topic,
            self.render_completed_topic,
            self.render_failed_topic,
            self.deployment_request_topic,
            self.deployment_completed_topic,
            self.deployment_failed_topic,
        }
        if len(topics) != 6:
            raise ValueError("all event topic names must be distinct")
        return self
