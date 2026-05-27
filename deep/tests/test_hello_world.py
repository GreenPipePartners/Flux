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
from flux_deep.rll import RllInstruction, RllProgram, RllRung, TagSeed, initial_state_from_tags


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

    assert "hello_TON(IN := NOT world_latch, PT := T#1s);" in st
    assert "world_TON(IN := world_latch, PT := T#1s);" in st
    assert "hello_world := hello;" in st
    assert "hello_world := world;" in st
    assert "PROGRAM MainInstance WITH Main : MainProgram;" in st


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


def test_rll_runtime_executes_bounded_hello_world_pulses() -> None:
    program = RllProgram(
        (
            RllRung.from_text_and_instructions(
                "XIO(world_latch)TON(hello_TON,?,?);",
                (
                    RllInstruction("XIO", ("world_latch",), "XIO(world_latch)"),
                    RllInstruction("TON", ("hello_TON", "?", "?"), "TON(hello_TON,?,?)"),
                ),
            ),
            RllRung.from_text_and_instructions(
                "XIC(hello_TON.DN)OTL(world_latch);",
                (
                    RllInstruction("XIC", ("hello_TON.DN",), "XIC(hello_TON.DN)"),
                    RllInstruction("OTL", ("world_latch",), "OTL(world_latch)"),
                ),
            ),
            RllRung.from_text_and_instructions(
                "XIC(world_latch)TON(world_TON,?,?);",
                (
                    RllInstruction("XIC", ("world_latch",), "XIC(world_latch)"),
                    RllInstruction("TON", ("world_TON", "?", "?"), "TON(world_TON,?,?)"),
                ),
            ),
            RllRung.from_text_and_instructions(
                "XIC(world_TON.DN)OTU(world_latch);",
                (
                    RllInstruction("XIC", ("world_TON.DN",), "XIC(world_TON.DN)"),
                    RllInstruction("OTU", ("world_latch",), "OTU(world_latch)"),
                ),
            ),
            RllRung.from_text_and_instructions(
                "[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ];",
                (
                    RllInstruction("XIO", ("world_latch",), "XIO(world_latch)"),
                    RllInstruction("COP", ("hello", "hello_world", "1"), "COP(hello,hello_world,1)"),
                    RllInstruction("XIC", ("world_latch",), "XIC(world_latch)"),
                    RllInstruction("COP", ("world", "hello_world", "1"), "COP(world,hello_world,1)"),
                ),
            ),
        )
    )
    state = initial_state_from_tags(
        (
            TagSeed("hello", "STRING", {"data": [{"format": "String", "text": "'hello'"}]}),
            TagSeed("world", "STRING", {"data": [{"format": "String", "text": "'world'"}]}),
            TagSeed("hello_world", "STRING", {"data": [{"format": "String", "text": "''"}]}),
            TagSeed("world_latch", "BOOL", {"data": [{"format": "L5K", "text": "0"}]}),
            TagSeed("hello_TON", "TIMER", {"data": [{"format": "L5K", "text": "[0,1000,0]"}]}),
            TagSeed("world_TON", "TIMER", {"data": [{"format": "L5K", "text": "[0,1000,0]"}]}),
        )
    )

    program.scan(state, scan_ms=100)
    assert state.values["hello_world"] == "hello"

    for _ in range(9):
        program.scan(state, scan_ms=100)
    assert state.values["world_latch"] is True
    assert state.values["hello_world"] == "world"

    for _ in range(9):
        program.scan(state, scan_ms=100)
    assert state.values["world_latch"] is False
    assert state.values["hello_world"] == "hello"


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
