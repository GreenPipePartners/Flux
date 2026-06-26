from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


def load_release_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_greenpipe_release.py"
    loader = importlib.machinery.SourceFileLoader("build_greenpipe_release", str(path))
    spec = importlib.util.spec_from_loader("build_greenpipe_release", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validate_release_tree_requires_flux_bootstrap(tmp_path: Path) -> None:
    release = load_release_script()

    with pytest.raises(SystemExit, match="flux_bootstrap.py"):
        release.validate_release_tree(tmp_path)


def test_validate_release_tree_accepts_flux_bootstrap(tmp_path: Path) -> None:
    release = load_release_script()
    command = tmp_path / "web" / "Flux" / "src" / "flux" / "base" / "management" / "commands" / "flux_bootstrap.py"
    command.parent.mkdir(parents=True)
    command.write_text("", encoding="utf-8")

    release.validate_release_tree(tmp_path)
