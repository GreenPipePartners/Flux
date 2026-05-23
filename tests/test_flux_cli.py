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


def test_mine_parse_l5x_wraps_core_package(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(["mine", "parse-l5x", "sample.L5X"])

    assert status == 0
    assert calls[0][0] == ["uv", "run", "--project", "mine", "flux-mine", "parse-l5x", "sample.L5X"]
    assert calls[0][1] == flux.ROOT_DIR


def test_mine_parse_l5k_wraps_core_package(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(["mine", "parse-l5k", "sample.L5K"])

    assert status == 0
    assert calls[0][0] == ["uv", "run", "--project", "mine", "flux-mine", "parse-l5k", "sample.L5K"]
    assert calls[0][1] == flux.ROOT_DIR


def test_mine_source_wraps_django_command(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(["mine", "source", "Screens", "--source-type", "factorytalk", "--label", "FTV"])

    assert status == 0
    assert calls[0][0] == [
        "uv",
        "run",
        "python",
        "manage.py",
        "flux_mine_source",
        "Screens",
        "--source-type",
        "factorytalk",
        "--label",
        "FTV",
    ]
    assert calls[0][1] == flux.WEB_DIR


def test_build_ignition_tags_wraps_core_package(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(["build", "ignition-tags", "sample.L5X", "--output", "provider.json"])

    assert status == 0
    assert calls[0][0] == [
        "uv",
        "run",
        "--project",
        "build",
        "flux-build",
        "ignition-tags",
        "sample.L5X",
        "--output",
        "provider.json",
    ]
    assert calls[0][1] == flux.ROOT_DIR


def test_build_ignition_tags_run_wraps_django_command(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_call(command, cwd=None, env=None):
        calls.append((command, cwd, env))
        return 0

    monkeypatch.setattr(flux.subprocess, "call", fake_call)

    status = flux.main(["build", "ignition-tags-run", "42", "--output", "provider.json"])

    assert status == 0
    assert calls[0][0] == [
        "uv",
        "run",
        "python",
        "manage.py",
        "flux_build_ignition_tags",
        "42",
        "--output",
        "provider.json",
    ]
    assert calls[0][1] == flux.WEB_DIR


def test_restart_stops_then_starts_service(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_run_script(name, env_updates=None):
        calls.append((name, env_updates))
        return 0

    monkeypatch.setattr(flux, "run_script", fake_run_script)

    status = flux.main(["restart"])

    assert status == 0
    assert calls == [("flux-service-stop", None), ("flux-service-start", {})]


def test_start_service_accepts_web_mode(monkeypatch):
    flux = load_flux_cli()
    calls = []

    def fake_run_script(name, env_updates=None):
        calls.append((name, env_updates))
        return 0

    monkeypatch.setattr(flux, "run_script", fake_run_script)

    status = flux.main(["start", "--web-mode", "dev"])

    assert status == 0
    assert calls == [("flux-service-start", {"FLUX_WEB_MODE": "dev"})]


def test_doctor_checks_docs_server(monkeypatch, capsys):
    flux = load_flux_cli()

    class Result:
        returncode = 0
        stdout = "active"
        stderr = ""

    def fake_capture(command, cwd=flux.ROOT_DIR):
        if command[:3] == ["uv", "run", "python"]:
            return type(
                "DoctorStateResult",
                (),
                {
                    "returncode": 0,
                    "stdout": '{"runtime":{"latest_read_age_seconds":0,"excluded_interface_tag_count":0,"tag_count":1,"stale_count":0,"bad_quality_count":0,"online_count":1},"bridge":{"online":true,"token_set":true,"base_url":"http://bridge","message":"","last_test_at":null},"historian":{"ok":true,"status":"Valid","db_type":"POSTGRES","database":"FluxyPostgres","error":""},"questdb":{"ok":true,"dsn":"qdb","trace_points":1}}',
                    "stderr": "",
                },
            )()
        return Result()

    def fake_check_http(url, timeout=3.0):
        return (url == flux.WEB_URL, "HTTP 200" if url == flux.WEB_URL else "connection refused")

    monkeypatch.setattr(flux, "capture", fake_capture)
    monkeypatch.setattr(flux, "check_http", fake_check_http)
    monkeypatch.setattr(flux, "check_port", lambda host, port, timeout=2.0: (True, "listening"))

    status = flux.doctor()

    output = capsys.readouterr().out
    assert status == 1
    assert "[FAIL] Flux docs: http://localhost:8001/ connection refused" in output
    assert "fix: flux docs serve" in output
