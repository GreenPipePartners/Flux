from __future__ import annotations

from flux_mine.hmi.tag_refs import parse_hmi_tag_reference
from flux_mine.plc.models import PlcController, PlcDataType, PlcMember, PlcProgram, PlcProject, PlcTag
from flux_mine.reconcile.plc_hmi import reconcile_hmi_tag_reference


def project_fixture() -> PlcProject:
    valve_type = PlcDataType(
        name="ValveT",
        members=(
            PlcMember(name="Cmd", data_type="BOOL"),
            PlcMember(name="Feedback", data_type="FeedbackT"),
        ),
    )
    feedback_type = PlcDataType(name="FeedbackT", members=(PlcMember(name="Device", data_type="DINT"),))
    controller = PlcController(
        name="PLC_01",
        data_types=(valve_type, feedback_type),
        tags=(
            PlcTag(name="Valve_01", data_type="ValveT"),
            PlcTag(name="Alias_Run", data_type="BOOL", tag_type="Alias", alias_for="Valve_01.Cmd"),
        ),
        programs=(
            PlcProgram(name="MainProgram", tags=(PlcTag(name="MachineState", data_type="DINT", scope="MainProgram"),)),
        ),
    )
    return PlcProject(controllers=(controller,))


def test_hmi_tag_reference_parses_factorytalk_prefix_and_program_scope() -> None:
    reference = parse_hmi_tag_reference("{/Area/Data Server::[FIS_PLC]Program:MainProgram.MachineState}")

    assert reference.shortcut == "FIS_PLC"
    assert reference.scope == "MainProgram"
    assert reference.base_tag == "MachineState"
    assert reference.member_path == ""


def test_reconcile_matches_udt_member_path_through_shortcut_map() -> None:
    reference = parse_hmi_tag_reference("[FIS_PLC]Valve_01.Feedback.Device")

    result = reconcile_hmi_tag_reference(reference, project_fixture(), {"FIS_PLC": "PLC_01"})

    assert result.status == "member"
    assert result.confidence == 0.95
    assert result.data_type == "DINT"


def test_reconcile_identifies_alias_and_missing_member() -> None:
    alias = parse_hmi_tag_reference("[FIS_PLC]Alias_Run")
    alias_result = reconcile_hmi_tag_reference(alias, project_fixture(), {"FIS_PLC": "PLC_01"})
    assert alias_result.status == "alias"
    assert alias_result.alias_for == "Valve_01.Cmd"

    missing = parse_hmi_tag_reference("[FIS_PLC]Valve_01.Unknown")
    missing_result = reconcile_hmi_tag_reference(missing, project_fixture(), {"FIS_PLC": "PLC_01"})
    assert missing_result.status == "missing_member"
