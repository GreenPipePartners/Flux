from __future__ import annotations

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
