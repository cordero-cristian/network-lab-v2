from __future__ import annotations

import importlib
import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest
from pydantic import ValidationError

from network_automation.settings import LabSettings


BASE_ENV = {
    "NAUTOBOT_SUPERUSER_PASSWORD": "local-password",
    "NAUTOBOT_SUPERUSER_API_TOKEN": "0123456789abcdef0123456789abcdef01234567",
}


def settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> LabSettings:
    for key, value in (BASE_ENV | overrides).items():
        monkeypatch.setenv(key, value)
    return LabSettings(_env_file=None)


def test_defaults_and_derived_kafka_address(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    actual = LabSettings(_env_file=None)

    assert str(actual.nautobot_url) == "http://localhost:8000/"
    assert actual.temporal_address == "localhost:7233"
    assert actual.kafka_bootstrap_servers == "localhost:9092"
    assert actual.probe_timeout_seconds == 10
    assert actual.render_request_topic == "network.render.requested"
    assert actual.render_completed_topic == "network.render.completed"
    assert actual.render_failed_topic == "network.render.failed"
    assert actual.deployment_request_topic == "network.deployment.requested"
    assert actual.deployment_completed_topic == "network.deployment.completed"
    assert actual.deployment_failed_topic == "network.deployment.failed"
    assert actual.render_consumer_group == "network-automation-render-consumer"
    assert actual.temporal_task_queue == "network-automation"
    assert actual.device_username is None
    assert actual.device_password is None
    assert actual.device_gnmi_port == 57401
    assert actual.device_gnmi_timeout_seconds == 10
    assert actual.device_gnmi_tls_mode == "insecure"


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LAB_KAFKA_HOST_PORT", "19092")
    monkeypatch.setenv("LAB_TEMPORAL_ADDRESS", "temporal.example:17233")
    monkeypatch.setenv("LAB_RENDER_REQUEST_TOPIC", "requests.test")
    monkeypatch.setenv("LAB_RENDER_COMPLETED_TOPIC", "completed.test")
    monkeypatch.setenv("LAB_RENDER_FAILED_TOPIC", "failed.test")
    monkeypatch.setenv("LAB_DEPLOYMENT_REQUEST_TOPIC", "deploy.requests.test")
    monkeypatch.setenv("LAB_DEPLOYMENT_COMPLETED_TOPIC", "deploy.completed.test")
    monkeypatch.setenv("LAB_DEPLOYMENT_FAILED_TOPIC", "deploy.failed.test")
    monkeypatch.setenv("LAB_RENDER_CONSUMER_GROUP", "consumer.test")
    monkeypatch.setenv("LAB_TEMPORAL_TASK_QUEUE", "queue.test")
    monkeypatch.setenv("LAB_DEVICE_USERNAME", "admin")
    monkeypatch.setenv("LAB_DEVICE_PASSWORD", "device-password")
    monkeypatch.setenv("LAB_DEVICE_GNMI_PORT", "57402")
    monkeypatch.setenv("LAB_DEVICE_GNMI_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("LAB_DEVICE_GNMI_TLS_MODE", "insecure")

    actual = LabSettings(_env_file=None)

    assert actual.kafka_bootstrap_servers == "localhost:19092"
    assert actual.temporal_address == "temporal.example:17233"
    assert actual.render_request_topic == "requests.test"
    assert actual.render_completed_topic == "completed.test"
    assert actual.render_failed_topic == "failed.test"
    assert actual.deployment_request_topic == "deploy.requests.test"
    assert actual.deployment_completed_topic == "deploy.completed.test"
    assert actual.deployment_failed_topic == "deploy.failed.test"
    assert actual.render_consumer_group == "consumer.test"
    assert actual.temporal_task_queue == "queue.test"
    assert actual.device_username == "admin"
    assert actual.device_password is not None
    assert actual.device_password.get_secret_value() == "device-password"
    assert "device-password" not in repr(actual)
    assert actual.device_gnmi_port == 57402
    assert actual.device_gnmi_timeout_seconds == 9
    assert actual.device_gnmi_tls_mode == "insecure"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LAB_TEMPORAL_ADDRESS", "http://localhost:7233"),
        ("LAB_KAFKA_BOOTSTRAP_SERVERS", "localhost"),
        ("LAB_KAFKA_BOOTSTRAP_SERVERS", "localhost:99999"),
        ("LAB_COMPOSE_PROJECT", "Network Lab"),
        ("LAB_PROBE_TIMEOUT_SECONDS", "11"),
        ("LAB_RENDER_REQUEST_TOPIC", ""),
        ("LAB_RENDER_COMPLETED_TOPIC", "has spaces"),
        ("LAB_RENDER_FAILED_TOPIC", ".starts-with-dot"),
        ("LAB_DEPLOYMENT_REQUEST_TOPIC", "bad topic"),
        ("LAB_DEPLOYMENT_COMPLETED_TOPIC", "/bad"),
        ("LAB_DEPLOYMENT_FAILED_TOPIC", ""),
        ("LAB_RENDER_CONSUMER_GROUP", "bad/group"),
        ("LAB_TEMPORAL_TASK_QUEUE", "bad queue"),
        ("LAB_DEVICE_USERNAME", " "),
        ("LAB_DEVICE_GNMI_PORT", "0"),
        ("LAB_DEVICE_GNMI_PORT", "65536"),
        ("LAB_DEVICE_GNMI_TIMEOUT_SECONDS", "0"),
        ("LAB_DEVICE_GNMI_TIMEOUT_SECONDS", "11"),
        ("LAB_DEVICE_GNMI_TLS_MODE", "secure"),
    ],
)
def test_invalid_settings_fail(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    for key, base_value in BASE_ENV.items():
        monkeypatch.setenv(key, base_value)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        LabSettings(_env_file=None)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LAB_RENDER_COMPLETED_TOPIC", "network.render.requested"),
        ("LAB_DEPLOYMENT_REQUEST_TOPIC", "network.render.failed"),
        ("LAB_DEPLOYMENT_FAILED_TOPIC", "network.deployment.completed"),
    ],
)
def test_all_six_event_topics_must_be_distinct(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    for key, base_value in BASE_ENV.items():
        monkeypatch.setenv(key, base_value)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        LabSettings(_env_file=None)


def test_pygnmi_exact_version_and_client_import() -> None:
    pyproject = tomllib.loads(
        (Path(__file__).parents[2] / "pyproject.toml").read_text(encoding="ascii")
    )
    assert "pygnmi==0.8.15" in pyproject["project"]["dependencies"]
    assert version("pygnmi") == "0.8.15"
    module = importlib.import_module("pygnmi.client")
    assert module.gNMIclient is not None


def test_required_secrets_and_secret_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NAUTOBOT_SUPERUSER_PASSWORD", raising=False)
    monkeypatch.delenv("NAUTOBOT_SUPERUSER_API_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        LabSettings(_env_file=None)

    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    actual = LabSettings(_env_file=None)
    assert "local-password" not in repr(actual)
    assert actual.nautobot_password.get_secret_value() == "local-password"


def test_import_does_not_construct_settings_or_call_external_systems() -> None:
    module = importlib.import_module("network_automation.settings")
    importlib.reload(module)


def test_environment_takes_precedence_over_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NAUTOBOT_SUPERUSER_PASSWORD=file-password\n"
        "NAUTOBOT_SUPERUSER_API_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "LAB_KAFKA_HOST_PORT=29092\n",
        encoding="ascii",
    )
    monkeypatch.setenv("NAUTOBOT_SUPERUSER_PASSWORD", "environment-password")
    monkeypatch.setenv(
        "NAUTOBOT_SUPERUSER_API_TOKEN", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    )
    monkeypatch.setenv("LAB_KAFKA_HOST_PORT", "39092")

    actual = LabSettings(_env_file=env_file)

    assert actual.nautobot_password.get_secret_value() == "environment-password"
    assert actual.kafka_bootstrap_servers == "localhost:39092"
