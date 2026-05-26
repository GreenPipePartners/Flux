from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from flux_deep.hello_world import (
    L5X_RELATIVE_PATH,
    MANIFEST_RELATIVE_PATH,
    OPENPLC_ST_RELATIVE_PATH,
    README_RELATIVE_PATH,
    hello_world_workspace,
    render_hello_world_l5x,
    render_hello_world_manifest,
    render_openplc_hello_world_st,
    write_hello_world_workspace,
)


def test_hello_world_l5x_declares_ladder_program_and_tags() -> None:
    root = ET.fromstring(render_hello_world_l5x())
    controller = first_descendant(root, "Controller")
    assert controller.attrib["Name"] == "hello_world"

    tags = {tag.attrib["Name"]: tag for tag in descendants(controller, "Tag")}
    assert tags["CycleCount"].attrib["DataType"] == "DINT"
    assert tags["CycleTimer"].attrib["DataType"] == "TIMER"
    assert tags["DisplayText"].attrib["DataType"] == "STRING"
    assert tags["HelloText"].attrib["DataType"] == "STRING"
    assert tags["WorldText"].attrib["DataType"] == "STRING"

    program = first_descendant(controller, "Program")
    assert program.attrib["Name"] == "MainProgram"
    routine = first_descendant(program, "Routine")
    assert routine.attrib["Type"] == "RLL"

    rung_texts = [text.text for text in descendants(routine, "Text")]
    assert "XIO(CycleTimer.DN)TON(CycleTimer,?,1000,0);" in rung_texts
    assert "XIC(CycleTimer.DN)ADD(CycleCount,1,CycleCount)RES(CycleTimer);" in rung_texts
    assert "XIC(CycleCount.0)COP(HelloText,DisplayText,1);" in rung_texts
    assert "XIO(CycleCount.0)COP(WorldText,DisplayText,1);" in rung_texts


def test_openplc_st_matches_hello_world_cycle_intent() -> None:
    st = render_openplc_hello_world_st()

    assert "cycle_timer(IN := timer_enable, PT := T#1s);" in st
    assert "display_text := 'hello';" in st
    assert "display_text := 'world';" in st
    assert "PROGRAM MainInstance WITH Main : hello_world;" in st


def test_manifest_tracks_source_and_runtime_targets() -> None:
    manifest = json.loads(render_hello_world_manifest())

    assert manifest["schema"] == "flux.deep.workspace.v1"
    assert manifest["runtime_backend"] == "openplc"
    assert manifest["source_entrypoint"] == "hello_world.l5x"
    assert manifest["openplc_entrypoint"] == "openplc/hello_world.st"
    assert manifest["cycle_seconds"] == 1


def test_workspace_writes_expected_files(tmp_path: Path) -> None:
    written = write_hello_world_workspace(tmp_path)

    assert sorted(path.relative_to(tmp_path) for path in written) == sorted(
        [L5X_RELATIVE_PATH, OPENPLC_ST_RELATIVE_PATH, MANIFEST_RELATIVE_PATH, README_RELATIVE_PATH]
    )
    assert (tmp_path / L5X_RELATIVE_PATH).exists()
    assert (tmp_path / OPENPLC_ST_RELATIVE_PATH).exists()

    with pytest.raises(FileExistsError):
        write_hello_world_workspace(tmp_path)

    write_hello_world_workspace(tmp_path, overwrite=True)


def test_checked_in_example_matches_generator() -> None:
    example_root = Path(__file__).resolve().parents[1] / "examples" / "hello_world"
    for file in hello_world_workspace().files:
        assert (example_root / file.relative_path).read_text(encoding="utf-8") == file.content


def descendants(node: ET.Element, name: str) -> list[ET.Element]:
    return [candidate for candidate in node.iter() if local_name(candidate.tag) == name]


def first_descendant(node: ET.Element, name: str) -> ET.Element:
    matches = descendants(node, name)
    assert matches, f"Expected XML descendant named {name}"
    return matches[0]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag
