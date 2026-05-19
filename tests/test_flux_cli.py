from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path


def load_flux_cli():
    path = Path(__file__).resolve().parents[1] / "scripts" / "flux"
    loader = importlib.machinery.SourceFileLoader("flux_cli", str(path))
    spec = importlib.util.spec_from_loader("flux_cli", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_check_port_reports_closed_port():
    flux = load_flux_cli()

    ok, detail = flux.check_port("localhost", 9, timeout=0.01)

    assert ok is False
    assert detail


def test_print_check_formats_status(capsys):
    flux = load_flux_cli()

    flux.print_check(True, "Example", "ready")
    flux.print_check(False, "Example", "broken")
    flux.print_fix("flux start")

    output = capsys.readouterr().out
    assert "[OK] Example: ready" in output
    assert "[FAIL] Example: broken" in output
    assert "fix: flux start" in output


def test_field_import_tag_data_wraps_manage_command(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(
        [
            "field",
            "import-tag-data",
            "Tag_02",
            "--devices",
            "tag_data/tag_data/tag_02 devices.txt",
            "--tags",
            "tag_data/tag_data/tags02.json",
        ]
    )

    assert status == 0
    assert calls[0][0][:4] == ["uv", "run", "python", "manage.py"]
    assert calls[0][0][4:] == [
        "import_tag_data_catalog",
        "Tag_02",
        "--devices",
        "tag_data/tag_data/tag_02 devices.txt",
        "--tags",
        "tag_data/tag_data/tags02.json",
    ]
    assert calls[0][1] == flux.WEB_DIR


def test_field_import_live_wraps_manage_command(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(
        [
            "field",
            "import-live",
            "default",
            "--provider",
            "Live_01",
            "--base-url",
            "http://gateway/flux",
            "--token",
            "secret",
        ]
    )

    assert status == 0
    assert calls[0][0][:5] == ["uv", "run", "python", "manage.py", "import_live_tag_catalog"]
    assert calls[0][0][5:] == [
        "default",
        "--base-url",
        "http://gateway/flux",
        "--token",
        "secret",
        "--provider",
        "Live_01",
    ]
    assert calls[0][1] == flux.WEB_DIR


def test_field_configure_ignition_wraps_manage_command(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(
        [
            "field",
            "configure-ignition",
            "--base-url",
            "http://gateway/system/webdev/flux",
            "--token",
            "secret",
            "--tag-provider",
            "default",
            "--tag-folder",
            "FieldAgent",
        ]
    )

    assert status == 0
    assert calls[0][0][:5] == ["uv", "run", "python", "manage.py", "configure_field_ignition"]
    assert "--token" in calls[0][0]
    assert "secret" in calls[0][0]
    assert calls[0][1] == flux.WEB_DIR
