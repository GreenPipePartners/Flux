from __future__ import annotations

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
