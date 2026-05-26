from __future__ import annotations

import json
from pathlib import Path

from flux_deep.cli import main


def test_init_hello_world_writes_workspace(tmp_path: Path, capsys) -> None:
    status = main(["init-hello-world", "--output", str(tmp_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "hello_world.l5x" in output
    assert (tmp_path / "hello_world.l5x").exists()
    assert (tmp_path / "openplc" / "hello_world.st").exists()


def test_inspect_prints_manifest(tmp_path: Path, capsys) -> None:
    main(["init-hello-world", "--output", str(tmp_path)])
    capsys.readouterr()

    status = main(["inspect", str(tmp_path)])

    manifest = json.loads(capsys.readouterr().out)
    assert status == 0
    assert manifest["name"] == "hello_world"
    assert manifest["runtime_backend"] == "openplc"
