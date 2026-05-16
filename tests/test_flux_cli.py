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
