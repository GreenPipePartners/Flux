from __future__ import annotations

from pathlib import Path

from flux_mine.plc.l5x import parse_l5x_file
from flux_mine.plc.l5x import parse_l5x_text


def test_l5x_parser_preserves_controller_tags_udts_and_member_metadata() -> None:
    project = parse_l5x_text(
        """
        <RSLogix5000Content xmlns="http://example.invalid/l5x">
          <Controller Name="PLC_01" ProcessorType="1756-L83E" MajorRev="35" CommPath="AB_ETHIP-1\\1.2.3.4">
            <DataTypes>
              <DataType Name="ValveT">
                <Description>Valve block</Description>
                <Members>
                  <Member Name="Cmd" DataType="BOOL" ExternalAccess="Read/Write" />
                  <Member Name="Packed" DataType="SINT" Hidden="true" />
                  <Member Name="Open" DataType="BIT" Target="Packed" BitNumber="0" Radix="Decimal" />
                </Members>
              </DataType>
            </DataTypes>
            <AddOnInstructionDefinitions>
              <AddOnInstructionDefinition Name="MotorAOI">
                <Parameters>
                  <Parameter Name="Run" DataType="BOOL" Usage="Input" Required="true" Visible="false" />
                </Parameters>
                <LocalTags>
                  <LocalTag Name="Timer" DataType="TIMER" />
                </LocalTags>
              </AddOnInstructionDefinition>
            </AddOnInstructionDefinitions>
            <Tags>
              <Tag Name="Valve_01" TagType="Base" DataType="ValveT" ExternalAccess="Read/Write" />
              <Tag Name="Samples" TagType="Base" DataType="REAL" Dimensions="20" />
              <Tag Name="Alias_Run" TagType="Alias" DataType="BOOL" AliasFor="Valve_01.Cmd" />
            </Tags>
            <Programs>
              <Program Name="MainProgram">
                <Tags>
                  <Tag Name="MachineState" TagType="Base" DataType="DINT" Dimension="5" />
                </Tags>
              </Program>
            </Programs>
          </Controller>
        </RSLogix5000Content>
        """.strip()
    )

    controller = project.controller_named("PLC_01")
    assert controller is not None
    assert controller.processor_type == "1756-L83E"
    assert controller.major_version == 35
    assert len(controller.data_types) == 2

    valve_type = controller.data_type_named("ValveT")
    assert valve_type is not None
    assert valve_type.description == "Valve block"
    open_member = valve_type.member_named("Open")
    assert open_member is not None
    assert open_member.is_packed_bit is True
    assert open_member.target == "Packed"
    assert open_member.bit_number == 0

    aoi = controller.data_type_named("MotorAOI")
    assert aoi is not None
    assert aoi.is_aoi is True
    assert {member.name for member in aoi.members} == {"Run", "Timer"}

    samples = controller.global_tag_named("Samples")
    assert samples is not None
    assert samples.array_dimensions == (20,)
    program_tag = controller.tag_named("MainProgram", "MachineState")
    assert program_tag is not None
    assert program_tag.array_dimensions == (5,)


def test_l5x_parser_preserves_hello_world_task_routine_rungs_and_tag_data() -> None:
    project = parse_l5x_file(repo_root() / "logix_samples" / "hello_world.L5X")

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

    hello = controller.tag_named("MainProgram", "hello")
    assert hello is not None
    assert hello.raw["data"][1]["format"] == "String"
    assert "'hello'" in hello.raw["data"][1]["text"]

    routine = program.routines[0]
    assert routine.name == "MainRoutine"
    assert routine.routine_type == "RLL"
    assert [rung.number for rung in routine.rungs] == [0, 1, 2, 3, 4]
    assert routine.rungs[4].text == "[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ];"

    instructions = [instruction for rung in routine.rungs for instruction in rung.instructions]
    references = [reference for instruction in instructions for reference in instruction.tag_references]
    assert [instruction.mnemonic for instruction in instructions[:4]] == ["XIO", "TON", "XIC", "OTL"]
    assert len(instructions) == 12
    assert len(references) == 14
    assert references[0].base_tag == "world_latch"
    assert references[0].role == "read"
    assert references[2].base_tag == "hello_TON"
    assert references[2].member_path == "DN"
    assert references[2].role == "read"
    assert [reference.role for reference in instructions[-1].tag_references] == ["source", "destination"]

    task = controller.task_named("MainTask")
    assert task is not None
    assert task.task_type == "CONTINUOUS"
    assert task.priority == 10
    assert task.watchdog == 500
    assert task.scheduled_programs == ("MainProgram",)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
