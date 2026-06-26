from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest


def load_installer():
    path = Path(__file__).resolve().parents[1] / "install" / "flux_installer.py"
    loader = importlib.machinery.SourceFileLoader("flux_installer", str(path))
    spec = importlib.util.spec_from_loader("flux_installer", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_config_reuses_existing_local_database_url(tmp_path: Path) -> None:
    installer = load_installer()
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    database_url = "postgres://flux:old%40pass@localhost:5432/flux"
    (config_dir / "flux.env").write_text(
        "DATABASE_URL=%s\nDJANGO_SECRET_KEY=old-secret\n" % database_url,
        encoding="utf-8",
    )

    args = installer.parse_args(["--config-dir", str(config_dir), "--no-prompt-db-password"])

    cfg = installer.default_config(args)

    assert cfg.database_url == database_url
    assert cfg.db_password == "old@pass"
    assert cfg.django_secret_key == "old-secret"
    assert cfg.skip_postgres_setup is False


def test_default_config_rejects_mismatched_password_without_force_env(tmp_path: Path) -> None:
    installer = load_installer()
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    (config_dir / "flux.env").write_text(
        "DATABASE_URL=postgres://flux:old-pass@localhost:5432/flux\n",
        encoding="utf-8",
    )

    args = installer.parse_args(
        ["--config-dir", str(config_dir), "--db-password", "new-pass", "--no-prompt-db-password"]
    )

    with pytest.raises(SystemExit, match="--force-env"):
        installer.default_config(args)


def test_default_config_prompts_for_fresh_interactive_local_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installer = load_installer()
    config_dir = tmp_path / "etc"
    prompts: list[str] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return "typed/secret"

    monkeypatch.setattr(installer.os, "geteuid", lambda: 0)
    monkeypatch.setattr(installer.os, "isatty", lambda _fd: True)
    monkeypatch.setattr(installer.getpass, "getpass", fake_getpass)

    args = installer.parse_args(["--config-dir", str(config_dir)])

    cfg = installer.default_config(args)

    assert len(prompts) == 2
    assert cfg.db_password == "typed/secret"
    assert cfg.database_url == "postgres://flux:typed%2Fsecret@localhost:5432/flux"
    assert cfg.skip_postgres_setup is False


def test_default_config_reuses_existing_external_database_url(tmp_path: Path) -> None:
    installer = load_installer()
    config_dir = tmp_path / "etc"
    config_dir.mkdir()
    database_url = "postgres://flux:secret@db-host:5432/flux"
    (config_dir / "flux.env").write_text("DATABASE_URL=%s\n" % database_url, encoding="utf-8")

    args = installer.parse_args(["--config-dir", str(config_dir), "--no-prompt-db-password"])

    cfg = installer.default_config(args)

    assert cfg.database_url == database_url
    assert cfg.skip_postgres_setup is True


def test_static_assets_stage_runs_before_systemd() -> None:
    installer = load_installer()
    names = [stage.name for stage in installer.STAGES]

    assert names.index("env") < names.index("static-assets") < names.index("systemd")
