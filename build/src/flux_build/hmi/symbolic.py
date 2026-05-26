from __future__ import annotations

from flux_build.hmi.models import HmiMapBuildResult, HmiMapComponent, HmiMapProject, HmiMapScreen
from flux_build.hmi.render_svg import render_hmi_map_svg


SYMBOLS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("button", "pushbutton", "momentary", "maintained"), "control.button", "B"),
    (("stringinput", "stringdisplay", "textinput"), "field.string", "S"),
    (("numericinput", "numericdisplay", "scale", "gauge"), "field.numeric", "N"),
    (("multistate", "indicator", "status"), "indicator.state", "I"),
    (("group",), "container.group", "G"),
    (("globalobject", "templateholder"), "reference.global_object", "O"),
    (("rectangle", "ellipse", "line", "polygon", "polyline"), "primitive.shape", "P"),
)


def build_symbolic_hmi_map(project: HmiMapProject) -> HmiMapBuildResult:
    screens: list[HmiMapScreen] = []
    for screen in project.screens:
        components = tuple(classified_component(component) for component in screen.components)
        screens.append(
            HmiMapScreen(
                screen_key=screen.screen_key,
                name=screen.name,
                source_path=screen.source_path,
                screen_type=screen.screen_type,
                width=screen.width,
                height=screen.height,
                components=components,
            )
        )
    mapped_project = HmiMapProject(screens=tuple(screens), source_path=project.source_path, source_sha256=project.source_sha256)
    svg_by_screen = {screen.screen_key: render_hmi_map_svg(screen) for screen in mapped_project.screens}
    return HmiMapBuildResult(project=mapped_project, svg_by_screen=svg_by_screen)


def classified_component(component: HmiMapComponent) -> HmiMapComponent:
    category, symbol = classify_component(component.vendor_type, component.global_object_reference)
    return HmiMapComponent(
        component_key=component.component_key,
        parent_key=component.parent_key,
        name=component.name,
        vendor_type=component.vendor_type,
        category=category,
        symbol=symbol,
        bounds=component.bounds,
        tag_references=component.tag_references,
        global_object_reference=component.global_object_reference,
        raw=component.raw,
    )


def classify_component(vendor_type: str, global_object_reference: str = "") -> tuple[str, str]:
    if global_object_reference:
        return "reference.global_object", "O"
    normalized = vendor_type.replace("_", "").replace("-", "").lower()
    for tokens, category, symbol in SYMBOLS:
        if any(token in normalized for token in tokens):
            return category, symbol
    return "primitive.unknown", "?"
