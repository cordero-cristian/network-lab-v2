from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from network_automation.api.models import (
    ArtifactSummary,
    ComparisonSources,
    ConfigurationDriftObservation,
    DeviceDetail,
    OperationalHealthObservation,
    SourceAvailability,
)
from network_automation.devices.comparison import (
    ConfigurationCheck,
    ConfigurationDriftResult,
    OperationalHealthCheck,
    OperationalHealthResult,
)


def test_source_availability_is_strict_and_serializes_utc() -> None:
    value = SourceAvailability(
        source="nautobot", status="healthy", observed_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        duration_ms=4, code="ok",
    )

    assert value.model_dump(mode="json")["observed_at"] == "2026-09-14T00:00:00Z"
    with pytest.raises(ValidationError):
        SourceAvailability(
            source="nautobot", status="healthy", observed_at=datetime(2026, 9, 14), code="ok"
        )
    with pytest.raises(ValidationError):
        SourceAvailability(
            source="nautobot", status="healthy", observed_at=datetime.now(timezone.utc),
            duration_ms="4", code="ok",
        )


def test_source_availability_rejects_raw_failure_text_and_unknown_codes() -> None:
    with pytest.raises(ValidationError):
        SourceAvailability(
            source="temporal", status="unavailable", observed_at=datetime.now(timezone.utc),
            code="password=secret", message="x" * 161,
        )


@pytest.mark.parametrize(
    "path",
    (".", "/etc/passwd", "../secret", "configs/../secret", "configs//leaf.cfg", "configs\\leaf.cfg"),
)
def test_artifact_summary_rejects_unconfined_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactSummary(relative_path=path, available=False)


def test_artifact_summary_accepts_normalized_root_relative_metadata() -> None:
    artifact = ArtifactSummary(relative_path="configs/leaf01.cfg", available=False)

    assert artifact.relative_path == "configs/leaf01.cfg"


def _sources(observed_at: datetime) -> ComparisonSources:
    return ComparisonSources(
        intent=SourceAvailability(
            source="nautobot", status="healthy", observed_at=observed_at, code="ok"
        ),
        device=SourceAvailability(
            source="device", status="healthy", observed_at=observed_at, code="ok"
        ),
    )


def test_comparison_observations_enforce_status_result_and_timestamp_invariants() -> None:
    observed_at = datetime(2026, 9, 22, tzinfo=timezone.utc)
    sources = _sources(observed_at)
    configuration = ConfigurationDriftResult(
        device_name="leaf01",
        status="in_sync",
        checks=(
            ConfigurationCheck(
                key="system.hostname",
                category="hostname",
                status="match",
                expected="leaf01",
                observed="leaf01",
                message=None,
            ),
        ),
        matches=1,
        mismatches=0,
        observed_at=observed_at,
    )
    operational = OperationalHealthResult(
        device_name="leaf01",
        status="healthy",
        checks=(
            OperationalHealthCheck(
                key="interface.system0.oper_state",
                category="interface_oper",
                status="healthy",
                expected="up",
                observed="up",
                message=None,
            ),
        ),
        healthy_count=1,
        unhealthy_count=0,
        unavailable_count=0,
        observed_at=observed_at,
    )

    drift = ConfigurationDriftObservation(
        status="in_sync", sources=sources, result=configuration, observed_at=observed_at
    )
    health = OperationalHealthObservation(
        status="healthy", sources=sources, result=operational, observed_at=observed_at
    )

    assert drift.result is configuration
    assert health.result is operational
    with pytest.raises(ValidationError):
        ConfigurationDriftObservation(
            status="unavailable", sources=sources, result=configuration, observed_at=observed_at
        )
    with pytest.raises(ValidationError):
        OperationalHealthObservation(
            status="healthy", sources=sources, result=None, observed_at=observed_at
        )
    with pytest.raises(ValidationError):
        ConfigurationDriftObservation(
            status="unavailable", sources=sources, result=None, observed_at=observed_at
        )
    with pytest.raises(ValidationError):
        OperationalHealthObservation(
            status="unavailable", sources=sources, result=None, observed_at=observed_at
        )
    with pytest.raises(ValidationError):
        ConfigurationDriftObservation(
            status="in_sync",
            sources=sources,
            result=configuration,
            observed_at=datetime(2026, 9, 22, 0, 0, 1, tzinfo=timezone.utc),
        )


def test_comparison_sources_are_typed_and_legacy_live_state_is_forbidden() -> None:
    observed_at = datetime(2026, 9, 22, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        ComparisonSources(
            intent=SourceAvailability(
                source="device", status="healthy", observed_at=observed_at, code="ok"
            ),
            device=SourceAvailability(
                source="device", status="healthy", observed_at=observed_at, code="ok"
            ),
        )

    assert "live_state" not in DeviceDetail.model_fields
