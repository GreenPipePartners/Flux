from __future__ import annotations

from flux_build.targets.ignition_tags import build_ignition_provider
from flux_mine.plc.models import PlcController, PlcDataType, PlcMember, PlcProgram, PlcProject, PlcTag


def project_fixture() -> PlcProject:
    valve_type = PlcDataType(
        name="ValveT",
        members=(
            PlcMember(name="Cmd", data_type="BOOL", description="Command"),
            PlcMember(name="Position", data_type="REAL"),
            PlcMember(name="Hidden", data_type="SINT", hidden=True),
            PlcMember(name="ZZZZZZZZZZPacked", data_type="SINT", hidden=True),
        ),
    )
    controller = PlcController(
        name="PLC_01",
        data_types=(valve_type,),
        tags=(
            PlcTag(name="Valve_01", data_type="ValveT", description="Main valve"),
            PlcTag(name="Samples", data_type="REAL", array_dimensions=(10,)),
            PlcTag(name="RunAlias", data_type="BOOL", tag_type="Alias", alias_for="Valve_01.Cmd"),
            PlcTag(name="Motion", data_type="MOTION_GROUP"),
        ),
        programs=(PlcProgram(name="MainProgram", tags=(PlcTag(name="MachineState", data_type="DINT", scope="MainProgram"),)),),
    )
    return PlcProject(controllers=(controller,))


def test_build_ignition_provider_generates_types_controller_and_program_tags() -> None:
    result = build_ignition_provider(project_fixture(), device_map={"PLC_01": "IgnitionDevice01"})
    provider = result.provider

    types = provider["tags"][0]
    assert types["name"] == "_types_"
    assert any(tag["name"] == "ValveT" for tag in types["tags"])
    assert any(tag["name"] == "TIMER" for tag in types["tags"])

    valve_type = next(tag for tag in types["tags"] if tag["name"] == "ValveT")
    member_names = {tag["name"] for tag in valve_type["tags"]}
    assert "Cmd" in member_names
    assert "Position" in member_names
    assert "ZZZZZZZZZZPacked" not in member_names

    controller = next(tag for tag in provider["tags"] if tag["name"] == "PLC_01")
    valve = next(tag for tag in controller["tags"] if tag["name"] == "Valve_01")
    assert valve["tagType"] == "UdtInstance"
    assert valve["typeId"] == "ValveT"
    assert "tags" not in valve
    assert valve["parameters"]["DeviceName"]["value"] == "IgnitionDevice01"

    samples = next(tag for tag in controller["tags"] if tag["name"] == "Samples")
    assert samples["dataType"] == "Float4Array"
    assert samples["opcItemPath"] == "ns=1;s=[IgnitionDevice01]Samples"

    program = next(tag for tag in controller["tags"] if tag["name"] == "MainProgram")
    machine_state = program["tags"][0]
    assert machine_state["opcItemPath"] == "ns=1;s=[IgnitionDevice01]Program:MainProgram.MachineState"


def test_build_ignition_provider_reports_skipped_unsupported_types() -> None:
    result = build_ignition_provider(project_fixture())

    assert any(diagnostic.code == "ignored_tag_type" for diagnostic in result.diagnostics)
    controller = next(tag for tag in result.provider["tags"] if tag["name"] == "PLC_01")
    assert "Motion" not in {tag["name"] for tag in controller["tags"]}
