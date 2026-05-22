from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path


def load_flux_test():
    path = Path(__file__).resolve().parents[1] / "test" / "flux_test.py"
    loader = importlib.machinery.SourceFileLoader("flux_test", str(path))
    spec = importlib.util.spec_from_loader("flux_test", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["flux_test"] = module
    spec.loader.exec_module(module)
    return module


def valid_manifest_data():
    return {
        "workspace": {
            "name": "Flux.test",
            "version": 1,
            "description": "Example manifest.",
        },
        "suite": [
            {
                "name": "fluxolot-fishtank",
                "description": "Fixture contract.",
                "command": ["uv", "run", "pytest"],
                "cwd": ".",
                "required_env": [],
                "timeout_seconds": 60,
                "external_services": [],
                "cleanup_expectations": "No cleanup.",
                "destructive_scope": "none",
            }
        ],
    }


def write_manifest(tmp_path, command, *, required_env=None):
    manifest_path = tmp_path / "manifest.toml"
    manifest_path.write_text(
        "\n".join(
            [
                "[workspace]",
                'name = "Flux.test"',
                "version = 1",
                'description = "Temp manifest."',
                "",
                "[[suite]]",
                'name = "temp-suite"',
                'description = "Temp suite."',
                "command = %s" % json.dumps(command),
                "cwd = %s" % json.dumps(str(tmp_path)),
                "required_env = %s" % json.dumps(required_env or []),
                "timeout_seconds = 5",
                "external_services = []",
                'cleanup_expectations = "No cleanup."',
                'destructive_scope = "none"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_parse_manifest_accepts_valid_suite_contract():
    flux_test = load_flux_test()

    manifest = flux_test.parse_manifest(valid_manifest_data())

    assert manifest.name == "Flux.test"
    assert manifest.version == 1
    assert manifest.suite_names() == ("fluxolot-fishtank",)
    suite = manifest.suites[0]
    assert suite.command == ("uv", "run", "pytest")
    assert suite.timeout_seconds == 60


def test_parse_manifest_rejects_missing_suite_field():
    flux_test = load_flux_test()
    data = valid_manifest_data()
    del data["suite"][0]["cleanup_expectations"]

    try:
        flux_test.parse_manifest(data)
    except flux_test.ManifestError as exc:
        assert "missing required field" in str(exc)
        assert "cleanup_expectations" in str(exc)
    else:
        raise AssertionError("Expected missing field validation error")


def test_parse_manifest_rejects_duplicate_suite_names():
    flux_test = load_flux_test()
    data = valid_manifest_data()
    data["suite"].append(dict(data["suite"][0]))

    try:
        flux_test.parse_manifest(data)
    except flux_test.ManifestError as exc:
        assert "Duplicate suite name" in str(exc)
        assert "fluxolot-fishtank" in str(exc)
    else:
        raise AssertionError("Expected duplicate suite validation error")


def test_suite_report_marks_missing_required_env_blocked():
    flux_test = load_flux_test()
    data = valid_manifest_data()
    data["suite"][0]["required_env"] = ["FLUX_TOKEN"]
    suite = flux_test.parse_manifest(data).suites[0]

    report = suite.report(Path("/repo"), environ={})

    assert report["status"] == "blocked"
    assert report["missing_env"] == ["FLUX_TOKEN"]
    assert report["report_only"] is True


def test_repo_manifest_loads_required_first_pass_suites():
    flux_test = load_flux_test()
    manifest_path = Path(__file__).resolve().parents[1] / "test" / "manifest.toml"

    manifest = flux_test.load_manifest(manifest_path)

    names = set(manifest.suite_names())
    assert {
        "fluxolot-fishtank",
        "live-csv",
        "trace-csv",
        "sampling",
        "sim-profile",
        "closed-loop",
        "unit-root",
        "unit-fluxy",
        "integration-fluxy",
        "unit-sim",
        "integration-sim",
        "unit-web",
        "integration-web",
    } <= names


def test_main_reports_selected_suite_without_running_command(capsys):
    flux_test = load_flux_test()

    status = flux_test.main(["fluxolot-fishtank"])

    output = capsys.readouterr().out
    assert status == 0
    assert "Report-only: commands are described, not executed." in output
    assert "[DEFINED] fluxolot-fishtank" in output
    assert "live-csv" not in output


def test_main_default_is_report_only_and_does_not_run_command(tmp_path, capsys):
    flux_test = load_flux_test()
    marker = tmp_path / "marker.txt"
    manifest_path = write_manifest(
        tmp_path,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('marker.txt').write_text('ran', encoding='utf-8')",
        ],
    )

    status = flux_test.main(["--manifest", str(manifest_path), "temp-suite"])

    output = capsys.readouterr().out
    assert status == 0
    assert "Report-only: commands are described, not executed." in output
    assert not marker.exists()


def test_main_execute_does_not_run_blocked_suite(tmp_path, capsys):
    flux_test = load_flux_test()
    marker = tmp_path / "marker.txt"
    manifest_path = write_manifest(
        tmp_path,
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('marker.txt').write_text('ran', encoding='utf-8')",
        ],
        required_env=["FLUX_TEST_DO_NOT_SET_BLOCKED_GATE"],
    )

    status = flux_test.main(["--manifest", str(manifest_path), "--execute", "--json", "temp-suite"])

    report = json.loads(capsys.readouterr().out)
    suite = report["suites"][0]
    assert status == 1
    assert suite["status"] == "blocked"
    assert suite["execution"]["status"] == "blocked"
    assert not marker.exists()


def test_main_execute_successful_command_reports_passed(tmp_path, capsys):
    flux_test = load_flux_test()
    manifest_path = write_manifest(tmp_path, [sys.executable, "-c", "print('hello flux')"])

    status = flux_test.main(["--manifest", str(manifest_path), "--execute", "--json", "temp-suite"])

    report = json.loads(capsys.readouterr().out)
    suite = report["suites"][0]
    assert status == 0
    assert report["report_only"] is False
    assert suite["status"] == "passed"
    assert suite["execution"]["status"] == "passed"
    assert suite["execution"]["returncode"] == 0
    assert "hello flux" in suite["execution"]["output"]


def test_main_execute_failing_command_returns_nonzero(tmp_path, capsys):
    flux_test = load_flux_test()
    manifest_path = write_manifest(tmp_path, [sys.executable, "-c", "import sys; sys.exit(7)"])

    status = flux_test.main(["--manifest", str(manifest_path), "--execute", "--json", "temp-suite"])

    report = json.loads(capsys.readouterr().out)
    suite = report["suites"][0]
    assert status == 1
    assert suite["status"] == "failed"
    assert suite["execution"]["status"] == "failed"
    assert suite["execution"]["returncode"] == 7
