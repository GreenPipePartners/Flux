from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from flux_deep.plc.plickir import PLCOPEN_NS, lift_rockwell_project
from flux_deep.plc.plickir.ld import render_plcopen_ld_project, write_plcopen_ld_project
from flux_mine.plc.l5x import parse_l5x_file


NS = {"plc": PLCOPEN_NS}


def test_plickir_renders_hello_world_as_openplc_editor_plcopen_ld() -> None:
    ir = lift_rockwell_project(parse_l5x_file(repo_root() / "logix_samples" / "hello_world.L5X"))

    xml_text = render_plcopen_ld_project(ir)
    root = ET.fromstring(xml_text)

    assert root.tag == f"{{{PLCOPEN_NS}}}project"
    pou = root.find(".//plc:pou[@name='MainProgram']", NS)
    assert pou is not None
    ld = pou.find("plc:body/plc:LD", NS)
    assert ld is not None
    assert ld.find("plc:leftPowerRail", NS) is not None
    assert ld.find("plc:rightPowerRail", NS) is not None

    variables = {
        variable.attrib["name"]: variable
        for variable in pou.findall("plc:interface/plc:localVars/plc:variable", NS)
    }
    assert variables["hello"].find("plc:type/plc:string", NS) is not None
    assert variables["hello"].find("plc:initialValue/plc:simpleValue", NS).attrib == {
        "value": "'hello'"
    }
    assert variables["world_latch"].find("plc:type/plc:BOOL", NS) is not None
    assert variables["hello_TON"].find("plc:type/plc:derived", NS).attrib == {"name": "TON"}

    contacts = ld.findall("plc:contact", NS)
    assert len(contacts) == 6
    assert contact_variables(contacts).count("world_latch") == 4
    assert "hello_TON.Q" in contact_variables(contacts)
    assert any(contact.attrib["negated"] == "true" for contact in contacts)

    coils = ld.findall("plc:coil", NS)
    assert {coil.attrib["storage"] for coil in coils} == {"set", "reset"}
    assert [coil.findtext("plc:variable", namespaces=NS) for coil in coils] == [
        "world_latch",
        "world_latch",
    ]

    ton_blocks = ld.findall("plc:block[@typeName='TON']", NS)
    assert [block.attrib["instanceName"] for block in ton_blocks] == ["hello_TON", "world_TON"]
    assert [node.findtext("plc:expression", namespaces=NS) for node in ld.findall("plc:inVariable", NS)].count(
        "T#1000ms"
    ) == 2

    move_blocks = ld.findall("plc:block[@typeName='MOVE']", NS)
    assert len(move_blocks) == 2
    assert [node.findtext("plc:expression", namespaces=NS) for node in ld.findall("plc:outVariable", NS)] == [
        "hello_world",
        "hello_world",
    ]

    task = root.find(".//plc:task[@name='MainTask']", NS)
    assert task is not None
    assert task.attrib["interval"] == "T#100ms"
    assert task.find("plc:pouInstance", NS).attrib == {
        "name": "MainProgramInstance",
        "typeName": "MainProgram",
    }


def test_plickir_writes_openplc_editor_project_folder(tmp_path: Path) -> None:
    ir = lift_rockwell_project(parse_l5x_file(repo_root() / "logix_samples" / "hello_world.L5X"))

    plc_xml = write_plcopen_ld_project(ir, tmp_path)

    assert plc_xml == tmp_path / "plc.xml"
    root = ET.fromstring(plc_xml.read_text(encoding="utf-8"))
    assert root.find(".//plc:pou[@name='MainProgram']/plc:body/plc:LD", NS) is not None


def contact_variables(contacts: list[ET.Element]) -> list[str]:
    return [contact.findtext("plc:variable", namespaces=NS) or "" for contact in contacts]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
