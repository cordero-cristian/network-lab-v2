from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from network_automation.api.models import ArtifactSummary, SourceAvailability


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
