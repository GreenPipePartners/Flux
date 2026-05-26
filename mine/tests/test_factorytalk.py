from __future__ import annotations

from flux_mine.hmi.factorytalk import parse_factorytalk_path, parse_factorytalk_xml_text


def test_factorytalk_xml_parser_recovers_components_and_tag_references() -> None:
    project_screen = parse_factorytalk_xml_text(
        """
        <gfx>
          <displaySettings width="1280" height="720" />
          <numericDisplay name="Pressure" left="10" top="20" width="100" height="30" tag="{[PLC]PT001.PV}" />
          <button name="Start" left="30" top="60" width="80" height="24">
            <action type="setToOne" tag="{[PLC]Program:MainProgram.StartCmd}" />
            <connections>
              <connection name="visible" expression="{[PLC]PT001.Enabled} == 1" />
            </connections>
          </button>
        </gfx>
        """.strip(),
        name="Overview.xml",
    )

    assert project_screen.name == "Overview.xml"
    assert project_screen.width == 1280
    assert len(project_screen.components) == 2
    references = project_screen.tag_references
    assert {reference.base_tag for reference in references} == {"PT001", "StartCmd"}
    program_reference = next(reference for reference in references if reference.base_tag == "StartCmd")
    assert program_reference.scope == "MainProgram"


def test_factorytalk_directory_parser_recovers_parameter_files(tmp_path) -> None:
    (tmp_path / "Screens").mkdir()
    (tmp_path / "Screens" / "Overview.xml").write_text(
        '<gfx><displaySettings width="800" height="600" /></gfx>',
        encoding="utf-8",
    )
    (tmp_path / "Valve.par").write_text("#1=[PLC]Valve01\n2, Pump A\n", encoding="utf-8")

    project = parse_factorytalk_path(tmp_path)

    assert project.summary()["screen_count"] == 1
    assert project.summary()["parameter_file_count"] == 1
    assert project.parameter_files[0].parameters == {"p1": "[PLC]Valve01", "p2": "Pump A"}
    assert project.source_sha256


def test_factorytalk_parser_preserves_hierarchy_and_enriched_component_facts() -> None:
    screen = parse_factorytalk_xml_text(
        """
        <gfx>
          <displaySettings width="1280" height="720" />
          <group name="PumpGroup">
            <numericDisplay name="Speed" left="10" top="20" width="100" height="30" tag="{[PLC]Pump01.Speed}" />
            <button name="Start" left="30" top="70" width="80" height="24" exposeToVba="vbaControl">
              <action type="setToOne" tag="{[PLC]Pump01.StartCmd}" />
            </button>
            <multiStateIndicator name="RunState" left="140" top="20" width="90" height="30">
              <states>
                <state stateId="1" value="{[PLC]Pump01.Running}" backColor="#00ff00">
                  <caption caption="Running" fontSize="12" color="#ffffff" />
                </state>
              </states>
            </multiStateIndicator>
            <globalObject name="PumpFaceplate" left="240" top="20" width="100" height="100" linkFile="Global Objects" linkObject="Pump" linkBaseObject="PumpTemplate">
              <parameters>
                <parameter name="#1" value="{[PLC]Pump01}" description="Pump root" />
              </parameters>
            </globalObject>
            <rectangle name="PumpBox" left="5" top="5" width="260" height="150" />
          </group>
        </gfx>
        """.strip(),
        name="Overview.xml",
    )

    group = next(component for component in screen.components if component.name == "PumpGroup")
    speed = next(component for component in screen.components if component.name == "Speed")
    start = next(component for component in screen.components if component.name == "Start")
    run_state = next(component for component in screen.components if component.name == "RunState")
    faceplate = next(component for component in screen.components if component.name == "PumpFaceplate")
    pump_box = next(component for component in screen.components if component.name == "PumpBox")

    assert group.is_group is True
    assert group.children_count == 5
    assert group.bounds == {"left": 5.0, "top": 5.0, "width": 335.0, "height": 150.0}
    assert speed.parent_path == group.component_path
    assert speed.depth == 1
    assert {reference.base_tag for reference in group.tag_references} == {"Pump01"}

    assert start.actions[0].action_type == "setToOne"
    assert start.actions[0].tag_references[0].member_path == "StartCmd"
    assert start.vba_links[0].name == "exposeToVba"

    assert run_state.states[0].caption == "Running"
    assert run_state.states[0].tag_references[0].member_path == "Running"

    assert faceplate.is_global_instance is True
    assert faceplate.global_object_link is not None
    assert faceplate.global_object_link.reference == "Global Objects/Pump"
    assert faceplate.parameters[0].name == "#1"
    assert faceplate.parameters[0].tag_references[0].base_tag == "Pump01"

    assert pump_box.geometry["geometry_type"] == "rectangle"
