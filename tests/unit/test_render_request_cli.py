from datetime import datetime, timezone
from uuid import UUID

import pytest

from network_automation.cli import render_request
from network_automation.events.models import RenderRequested, workflow_id_for
from network_automation.events.producer import EventPublishError


def test_cli_publishes_valid_request_then_prints_identifiers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    published: list[RenderRequested] = []
    before = datetime.now(timezone.utc)

    def publish(event: RenderRequested, *args: object, **kwargs: object) -> None:
        assert capsys.readouterr().out == ""
        published.append(event)

    monkeypatch.setattr(render_request, "publish_event", publish)

    assert render_request.main(["leaf01"]) == 0

    after = datetime.now(timezone.utc)
    event = published.pop()
    assert event.device_name == "leaf01"
    assert event.source == "cli"
    assert event.event_id != event.correlation_id
    assert before <= event.requested_at <= after
    assert event.requested_at.utcoffset() == timezone.utc.utcoffset(event.requested_at)
    output = capsys.readouterr()
    assert output.err == ""
    assert output.out.splitlines() == [
        f"event_id={event.event_id}",
        f"correlation_id={event.correlation_id}",
        f"workflow_id={workflow_id_for(event.event_id)}",
    ]


def test_cli_uses_new_identifiers_for_each_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[RenderRequested] = []
    monkeypatch.setattr(
        render_request, "publish_event", lambda event, *args, **kwargs: published.append(event)
    )

    assert render_request.main(["leaf01"]) == 0
    assert render_request.main(["leaf01"]) == 0

    assert len({event.event_id for event in published}) == 2
    assert len({event.correlation_id for event in published}) == 2
    assert all(isinstance(event.event_id, UUID) for event in published)


def test_cli_returns_nonzero_and_redacts_publication_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise EventPublishError("broker failure included super-secret")

    monkeypatch.setattr(render_request, "publish_event", fail)

    assert render_request.main(["leaf01"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: request publication failed (EventPublishError)\n"
    assert "super-secret" not in captured.err
