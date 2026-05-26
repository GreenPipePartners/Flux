from __future__ import annotations

from pathlib import Path

from flux_mine.plc.l5k import parse_l5k_file
from flux_mine.plc.l5k import parse_l5k_text
from flux_mine.plc.parsers import parse_plc_file


def test_l5k_parser_preserves_controller_udts_aoi_tags_and_program_scope() -> None:
    project = parse_l5k_text(
        """
        CONTROLLER PLC_Test (ProcessorType := "1768-L45", Major := 32, CommPath := "AB_ETHIP-1\\1.2.3.4")
            DATATYPE MyUDT (Description := "Unit data")
                DINT Status;
                Value : REAL (Description := "A Value", ExternalAccess := Read/Write);
                HiddenPacked : SINT (Hidden := 1);
            END_DATATYPE

            ADD_ON_INSTRUCTION_DEFINITION MyAOI
                LOCAL_TAGS
                    DINT LocalVal;
                END_LOCAL_TAGS
                PARAMETERS
                    InVal : REAL;
                END_PARAMETERS
            END_ADD_ON_INSTRUCTION_DEFINITION

            TAG
                PT001 : REAL (Description := "Pressure Trans");
                ArrayTag : DINT[10];
                AliasTag OF PT001;
                UDT_Tag : MyUDT;
            END_TAG

            PROGRAM MainProgram
                TAG
                    PCVD_Seal_Pressure : REAL;
                    LocalArr : REAL[5,5];
                END_TAG
            END_PROGRAM
        """.strip()
    )

    controller = project.controller_named("PLC_Test")
    assert controller is not None
    assert controller.processor_type == "1768-L45"
    assert controller.major_version == 32
    assert controller.comm_path == "AB_ETHIP-1\\1.2.3.4"

    my_udt = controller.data_type_named("MyUDT")
    assert my_udt is not None
    assert my_udt.description == "Unit data"
    assert {member.name for member in my_udt.members} == {"Status", "Value", "HiddenPacked"}
    value = my_udt.member_named("Value")
    assert value is not None
    assert value.description == "A Value"
    assert value.external_access == "Read/Write"
    hidden = my_udt.member_named("HiddenPacked")
    assert hidden is not None
    assert hidden.hidden is True

    my_aoi = controller.data_type_named("MyAOI")
    assert my_aoi is not None
    assert my_aoi.is_aoi is True
    assert {member.name for member in my_aoi.members} == {"LocalVal", "InVal"}

    assert len(controller.tags) == 4
    array_tag = controller.global_tag_named("ArrayTag")
    assert array_tag is not None
    assert array_tag.array_dimensions == (10,)
    alias = controller.global_tag_named("AliasTag")
    assert alias is not None
    assert alias.is_alias is True
    assert alias.alias_for == "PT001"

    program_tag = controller.tag_named("MainProgram", "LocalArr")
    assert program_tag is not None
    assert program_tag.array_dimensions == (5, 5)


def test_parse_plc_file_dispatches_l5k_by_extension(tmp_path) -> None:
    source = tmp_path / "sample.L5K"
    source.write_text(
        """
        CONTROLLER PLC_Test (ProcessorType := "1768-L45")
            TAG
                PT001 : REAL;
            END_TAG
        """.strip(),
        encoding="utf-8",
    )

    project = parse_plc_file(source)

    controller = project.controller_named("PLC_Test")
    assert controller is not None
    assert controller.global_tag_named("PT001") is not None
    assert project.source_sha256


def test_l5k_parser_preserves_hello_world_task_routine_and_rungs() -> None:
    project = parse_l5k_file(repo_root() / "logix_samples" / "hello_world.L5K")

    controller = project.controller_named("hello_world")
    assert controller is not None
    assert len(controller.tags) == 0
    assert len(controller.programs) == 1
    assert len(controller.tasks) == 1

    program = controller.program_named("MainProgram")
    assert program is not None
    assert program.main_routine_name == "MainRoutine"
    assert len(program.tags) == 6
    assert len(program.routines) == 1

    routine = program.routines[0]
    assert routine.name == "MainRoutine"
    assert routine.routine_type == "RLL"
    assert [rung.number for rung in routine.rungs] == [0, 1, 2, 3, 4]
    assert routine.rungs[4].text == "[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ]"

    instructions = [instruction for rung in routine.rungs for instruction in rung.instructions]
    references = [reference for instruction in instructions for reference in instruction.tag_references]
    assert len(instructions) == 12
    assert len(references) == 14
    assert instructions[-1].mnemonic == "COP"
    assert [reference.role for reference in instructions[-1].tag_references] == ["source", "destination"]

    task = controller.task_named("MainTask")
    assert task is not None
    assert task.task_type == "CONTINUOUS"
    assert task.rate == 10
    assert task.priority == 10
    assert task.watchdog == 500
    assert task.scheduled_programs == ("MainProgram",)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
