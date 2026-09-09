from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from network_automation.cli import render


def test_render_device_runs_complete_orchestration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}
    raw = {"raw": "intent"}
    intent = object()
    target = tmp_path / "device.cfg"

    class FakeClient:
        def __init__(self, url: str, token: str, *, timeout: float) -> None:
            calls["client"] = (url, token, timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            calls["closed"] = True

        def get_device_data(self, name: str) -> dict[str, str]:
            calls["name"] = name
            return raw

    monkeypatch.setattr(
        render,
        "LabSettings",
        lambda: SimpleNamespace(
            nautobot_url="http://nautobot.test/",
            nautobot_token=SecretStr("super-secret"),
            probe_timeout_seconds=7,
        ),
    )
    monkeypatch.setattr(render, "NautobotClient", FakeClient)
    monkeypatch.setattr(render, "device_intent_from_nautobot", lambda value: intent)

    def write(value: object, output_dir: Path) -> Path:
        calls["write"] = (value, output_dir)
        return target

    monkeypatch.setattr(render, "write_srlinux_artifact", write)

    assert render.render_device("device", tmp_path) == target
    assert calls == {
        "client": ("http://nautobot.test/", "super-secret", 7),
        "name": "device",
        "closed": True,
        "write": (intent, tmp_path),
    }


def test_cli_prints_path_after_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "device.cfg"
    monkeypatch.setattr(render, "render_device", lambda name, output_dir: target)

    assert render.main(["device", "--output-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == f"{target}\n"


def test_cli_returns_nonzero_without_leaking_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(name: str, output_dir: Path) -> Path:
        raise RuntimeError("failure included super-secret")

    monkeypatch.setattr(render, "render_device", fail)
    assert render.main(["device", "--output-dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: rendering failed (RuntimeError)\n"
    assert "super-secret" not in captured.err
