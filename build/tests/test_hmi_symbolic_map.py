from __future__ import annotations

from flux_build.hmi.models import HmiMapComponent, HmiMapProject, HmiMapScreen, HmiMapTagReference
from flux_build.hmi.symbolic import build_symbolic_hmi_map, classify_component


def test_classify_component_uses_vendor_neutral_symbols() -> None:
    assert classify_component("momentaryButton") == ("control.button", "B")
    assert classify_component("stringInput") == ("field.string", "S")
    assert classify_component("numericDisplay") == ("field.numeric", "N")
    assert classify_component("group") == ("container.group", "G")
    assert classify_component("anything", "Global/Pump") == ("reference.global_object", "O")
    assert classify_component("strangeThing") == ("primitive.unknown", "?")


def test_build_symbolic_hmi_map_preserves_bounds_tags_and_svg_nodes() -> None:
    project = HmiMapProject(
        screens=(
            HmiMapScreen(
                screen_key="Overview.xml",
                name="Overview.xml",
                width=800,
                height=600,
                components=(
                    HmiMapComponent(
                        component_key="0:numericDisplay:Pressure",
                        name="Pressure",
                        vendor_type="numericDisplay",
                        bounds={"left": 10, "top": 20, "width": 100, "height": 30},
                        tag_references=(HmiMapTagReference(original="{[PLC]PT001}", shortcut="PLC", base_tag="PT001"),),
                    ),
                    HmiMapComponent(
                        component_key="1:button:Start",
                        name="Start",
                        vendor_type="button",
                        bounds={"left": 30, "top": 70, "width": 80, "height": 24},
                    ),
                ),
            ),
        ),
    )

    result = build_symbolic_hmi_map(project)

    screen = result.project.screens[0]
    assert [component.symbol for component in screen.components] == ["N", "B"]
    assert screen.components[0].tag_references[0].base_tag == "PT001"
    assert 'data-hmi-map-node="0:numericDisplay:Pressure"' in result.svg_by_screen["Overview.xml"]
