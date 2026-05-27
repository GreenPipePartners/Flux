from __future__ import annotations

from pathlib import Path

from flux_deep.plc.plickir import PlickirTagRef, PlickirTimerInitial, lift_rockwell_project
from flux_mine.plc.l5x import parse_l5x_file


def test_plickir_lifts_hello_world_l5x_into_canonical_ir() -> None:
    source = repo_root() / "logix_samples" / "hello_world.L5X"

    ir = lift_rockwell_project(parse_l5x_file(source))

    assert ir.counts() == {
        "controller_count": 1,
        "program_count": 1,
        "task_count": 1,
        "routine_count": 1,
        "rung_count": 5,
        "network_count": 6,
        "instruction_count": 12,
        "diagnostic_count": 0,
    }

    controller = ir.controller_named("hello_world")
    assert controller is not None
    program = controller.program_named("MainProgram")
    assert program is not None
    assert program.main_routine_name == "MainRoutine"
    assert controller.tasks[0].scheduled_programs == ("MainProgram",)

    assert controller.tag_named("MainProgram", "hello").initial_value == "hello"
    assert controller.tag_named("MainProgram", "world").initial_value == "world"
    assert controller.tag_named("MainProgram", "world_latch").initial_value is False
    assert controller.tag_named("MainProgram", "hello_TON").initial_value == PlickirTimerInitial(
        preset_ms=1000,
        accumulated_ms=0,
    )

    routine = program.routines[0]
    assert [rung.number for rung in routine.rungs] == [0, 1, 2, 3, 4]
    assert [instruction.kind for instruction in routine.rungs[0].networks[0].instructions] == [
        "contact.nc",
        "timer.ton",
    ]
    assert [instruction.kind for instruction in routine.rungs[1].networks[0].instructions] == [
        "contact.no",
        "coil.latch",
    ]

    branch_rung = routine.rungs[4]
    assert len(branch_rung.networks) == 2
    assert [instruction.kind for instruction in branch_rung.networks[0].instructions] == [
        "contact.nc",
        "copy",
    ]
    assert [instruction.kind for instruction in branch_rung.networks[1].instructions] == [
        "contact.no",
        "copy",
    ]

    first_copy = branch_rung.networks[0].instructions[1]
    assert first_copy.operands == (
        PlickirTagRef("hello", scope="MainProgram"),
        PlickirTagRef("hello_world", scope="MainProgram"),
        1,
    )
    done_contact = routine.rungs[1].networks[0].instructions[0]
    assert done_contact.operands == (PlickirTagRef("hello_TON", scope="MainProgram", member_path="DN"),)
    assert done_contact.source.rung_number == 1
    assert done_contact.source.original == "XIC(hello_TON.DN)"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
