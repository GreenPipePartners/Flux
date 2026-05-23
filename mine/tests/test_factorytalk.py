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
