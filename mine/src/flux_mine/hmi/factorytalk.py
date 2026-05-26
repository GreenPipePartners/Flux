from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flux_mine.hmi.tag_refs import HmiTagReference, extract_hmi_tag_references


@dataclass(frozen=True)
class FactoryTalkAction:
    name: str
    action_type: str = ""
    value: str = ""
    tag_references: tuple[HmiTagReference, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkState:
    state_id: str = ""
    value: str = ""
    caption: str = ""
    back_color: str = ""
    border_color: str = ""
    border_width: str = ""
    font_size: str = ""
    font_family: str = ""
    text_color: str = ""
    tag_references: tuple[HmiTagReference, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkComponentParameter:
    name: str
    value: str = ""
    description: str = ""
    tag_references: tuple[HmiTagReference, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkGlobalObjectLink:
    reference: str = ""
    link_file: str = ""
    link_object: str = ""
    link_base_object: str = ""
    link_size: str = ""
    link_connections: str = ""
    link_animations: str = ""
    link_tooltip_text: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkVbaLink:
    name: str
    value: str = ""
    tag_references: tuple[HmiTagReference, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkComponent:
    name: str
    component_type: str
    component_path: str = ""
    parent_path: str = ""
    depth: int = 0
    sibling_index: int = 0
    children_count: int = 0
    is_group: bool = False
    is_global_instance: bool = False
    attributes: dict[str, str] = field(default_factory=dict)
    bounds: dict[str, float] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)
    global_object_reference: str = ""
    global_object_link: FactoryTalkGlobalObjectLink | None = None
    actions: tuple[FactoryTalkAction, ...] = ()
    states: tuple[FactoryTalkState, ...] = ()
    parameters: tuple[FactoryTalkComponentParameter, ...] = ()
    vba_links: tuple[FactoryTalkVbaLink, ...] = ()
    tag_references: tuple[HmiTagReference, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkScreen:
    name: str
    screen_type: str = "display"
    source_path: str = ""
    width: float | None = None
    height: float | None = None
    components: tuple[FactoryTalkComponent, ...] = ()

    @property
    def tag_references(self) -> tuple[HmiTagReference, ...]:
        return tuple(reference for component in self.components for reference in component.tag_references)

    @property
    def actions(self) -> tuple[FactoryTalkAction, ...]:
        return tuple(action for component in self.components for action in component.actions)

    @property
    def states(self) -> tuple[FactoryTalkState, ...]:
        return tuple(state for component in self.components for state in component.states)

    @property
    def component_parameters(self) -> tuple[FactoryTalkComponentParameter, ...]:
        return tuple(parameter for component in self.components for parameter in component.parameters)

    @property
    def vba_links(self) -> tuple[FactoryTalkVbaLink, ...]:
        return tuple(vba_link for component in self.components for vba_link in component.vba_links)


@dataclass(frozen=True)
class FactoryTalkParameterFile:
    name: str
    source_path: str = ""
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryTalkProject:
    screens: tuple[FactoryTalkScreen, ...] = ()
    parameter_files: tuple[FactoryTalkParameterFile, ...] = ()
    source_path: str = ""
    source_sha256: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "screen_count": len(self.screens),
            "component_count": sum(len(screen.components) for screen in self.screens),
            "tag_reference_count": sum(len(screen.tag_references) for screen in self.screens),
            "action_count": sum(len(screen.actions) for screen in self.screens),
            "state_count": sum(len(screen.states) for screen in self.screens),
            "component_parameter_count": sum(len(screen.component_parameters) for screen in self.screens),
            "global_object_link_count": sum(1 for screen in self.screens for component in screen.components if component.global_object_link),
            "vba_link_count": sum(len(screen.vba_links) for screen in self.screens),
            "parameter_file_count": len(self.parameter_files),
            "parameter_count": sum(len(parameter_file.parameters) for parameter_file in self.parameter_files),
        }


def parse_factorytalk_path(path: str | Path) -> FactoryTalkProject:
    source_path = Path(path)
    if source_path.is_dir():
        return parse_factorytalk_directory(source_path)
    if source_path.suffix.lower() == ".xml":
        screen = parse_factorytalk_xml_file(source_path, screen_type=screen_type_for_path(source_path))
        content = source_path.read_bytes()
        return FactoryTalkProject(
            screens=(screen,),
            source_path=str(source_path),
            source_sha256=hashlib.sha256(content).hexdigest(),
        )
    if source_path.suffix.lower() == ".par":
        parameter_file = parse_parameter_file(source_path)
        content = source_path.read_bytes()
        return FactoryTalkProject(
            parameter_files=(parameter_file,),
            source_path=str(source_path),
            source_sha256=hashlib.sha256(content).hexdigest(),
        )
    raise ValueError(f"Unsupported FactoryTalk source path: {source_path}")


def parse_factorytalk_directory(path: str | Path) -> FactoryTalkProject:
    source_path = Path(path)
    screens = tuple(
        parse_factorytalk_xml_file(xml_path, screen_type=screen_type_for_path(xml_path))
        for xml_path in sorted(source_path.rglob("*.xml"))
        if not ignored_factorytalk_xml(xml_path)
    )
    parameter_files = tuple(parse_parameter_file(par_path) for par_path in sorted(source_path.rglob("*.par")))
    return FactoryTalkProject(
        screens=screens,
        parameter_files=parameter_files,
        source_path=str(source_path),
        source_sha256=directory_sha256(source_path, (".xml", ".par")),
    )


def parse_factorytalk_xml_file(path: str | Path, *, screen_type: str = "display") -> FactoryTalkScreen:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_factorytalk_xml_text(text, source_path=str(source_path), name=source_path.name, screen_type=screen_type)


def parse_factorytalk_xml_text(
    text: str,
    *,
    source_path: str = "",
    name: str = "screen.xml",
    screen_type: str = "display",
) -> FactoryTalkScreen:
    root = ET.fromstring(text)
    width, height = display_dimensions(root)
    components: list[FactoryTalkComponent] = []
    collect_components(root, components, parent_path="", depth=0, inside_global_instance=False)
    return FactoryTalkScreen(
        name=name,
        screen_type=screen_type,
        source_path=source_path,
        width=width,
        height=height,
        components=tuple(components),
    )


def collect_components(
    node: ET.Element,
    components: list[FactoryTalkComponent],
    *,
    parent_path: str,
    depth: int,
    inside_global_instance: bool,
) -> None:
    component_children = [child for child in list(node) if is_component_node(local_name(child.tag), child.attrib)]
    child_component_index = 0
    for child in list(node):
        tag = local_name(child.tag)
        is_visual_component = is_component_node(tag, child.attrib)
        if not is_visual_component:
            collect_components(
                child,
                components,
                parent_path=parent_path,
                depth=depth,
                inside_global_instance=inside_global_instance,
            )
            continue

        component_path = component_key(parent_path, child_component_index, tag, child.attrib.get("name", f"Unnamed_{tag}"))
        is_global = is_global_instance_node(tag, child.attrib) and not inside_global_instance
        component = parse_component(
            child,
            tag=tag,
            component_path=component_path,
            parent_path=parent_path,
            depth=depth,
            sibling_index=child_component_index,
            children_count=count_component_children(child),
            is_global_instance=is_global,
        )
        components.append(component)
        child_component_index += 1

        if is_global:
            continue
        collect_components(
            child,
            components,
            parent_path=component_path,
            depth=depth + 1,
            inside_global_instance=inside_global_instance or is_global,
        )


def parse_component(
    node: ET.Element,
    *,
    tag: str,
    component_path: str,
    parent_path: str,
    depth: int,
    sibling_index: int,
    children_count: int,
    is_global_instance: bool,
) -> FactoryTalkComponent:
    component_bounds = bounds(node.attrib)
    if (tag == "group" or is_global_instance) and not has_complete_bounds(component_bounds):
        component_bounds = subtree_bounds(node)
    action_items = parse_actions(node)
    state_items = parse_states(node)
    parameter_items = parse_component_parameters(node)
    vba_items = parse_vba_links(node)
    global_link = parse_global_object_link(node.attrib) if is_global_instance else None
    references = merge_references(
        references_from_subtree(node),
        *(action.tag_references for action in action_items),
        *(state.tag_references for state in state_items),
        *(parameter.tag_references for parameter in parameter_items),
        *(vba_link.tag_references for vba_link in vba_items),
    )
    return FactoryTalkComponent(
        name=node.attrib.get("name", f"Unnamed_{tag}"),
        component_type=tag,
        component_path=component_path,
        parent_path=parent_path,
        depth=depth,
        sibling_index=sibling_index,
        children_count=children_count,
        is_group=tag == "group",
        is_global_instance=is_global_instance,
        attributes={key: value for key, value in node.attrib.items()},
        bounds=component_bounds,
        geometry=geometry(tag, node.attrib, component_bounds),
        global_object_reference=global_object_reference(node.attrib),
        global_object_link=global_link,
        actions=action_items,
        states=state_items,
        parameters=parameter_items,
        vba_links=vba_items,
        tag_references=references,
        raw={"tag": tag, "attributes": dict(node.attrib)},
    )


def parse_actions(node: ET.Element) -> tuple[FactoryTalkAction, ...]:
    actions: list[FactoryTalkAction] = []
    for key, value in node.attrib.items():
        if (key.endswith("Action") or key == "command") and value:
            actions.append(action_from_value(key, key, value, {"attributes": {key: value}}))
    for child in node:
        child_tag = local_name(child.tag)
        if child_tag == "command":
            for key, value in child.attrib.items():
                if (key.endswith("Action") or key == "command") and value:
                    actions.append(action_from_value(key, key, value, {"tag": child_tag, "attributes": dict(child.attrib)}))
        elif child_tag == "action":
            action_type = child.attrib.get("type", "")
            value = child.attrib.get("tag", "") or child.attrib.get("command", "") or child.attrib.get("expression", "")
            actions.append(action_from_value(action_type or "action", action_type, value, {"tag": child_tag, "attributes": dict(child.attrib)}))
        elif child_tag == "connections":
            for connection in child:
                if local_name(connection.tag) != "connection":
                    continue
                name = connection.attrib.get("name", "connection")
                value = connection.attrib.get("expression", "")
                if value:
                    actions.append(action_from_value(f"connection_{name}", "connection", value, {"tag": "connection", "attributes": dict(connection.attrib)}))
    return tuple(actions)


def action_from_value(name: str, action_type: str, value: str, raw: dict[str, Any]) -> FactoryTalkAction:
    return FactoryTalkAction(
        name=name,
        action_type=action_type,
        value=value,
        tag_references=extract_hmi_tag_references(value),
        raw=raw,
    )


def parse_states(node: ET.Element) -> tuple[FactoryTalkState, ...]:
    states: list[FactoryTalkState] = []
    for child in node:
        if local_name(child.tag) != "states":
            continue
        for state_node in child:
            if local_name(state_node.tag) != "state":
                continue
            caption = ""
            font_size = ""
            font_family = ""
            text_color = ""
            values = list(state_node.attrib.values())
            for state_child in state_node:
                if local_name(state_child.tag) == "caption":
                    caption = state_child.attrib.get("caption", "") or (state_child.text or "")
                    font_size = state_child.attrib.get("fontSize", "")
                    font_family = state_child.attrib.get("fontFamily", "")
                    text_color = state_child.attrib.get("color", "")
                values.extend(state_child.attrib.values())
                if state_child.text:
                    values.append(state_child.text)
            states.append(
                FactoryTalkState(
                    state_id=state_node.attrib.get("stateId", ""),
                    value=state_node.attrib.get("value", state_node.attrib.get("stateId", "")),
                    caption=caption,
                    back_color=state_node.attrib.get("backColor", ""),
                    border_color=state_node.attrib.get("borderColor", ""),
                    border_width=state_node.attrib.get("borderWidth", ""),
                    font_size=font_size,
                    font_family=font_family,
                    text_color=text_color,
                    tag_references=extract_references_from_values(values),
                    raw={"tag": "state", "attributes": dict(state_node.attrib)},
                )
            )
    return tuple(states)


def parse_component_parameters(node: ET.Element) -> tuple[FactoryTalkComponentParameter, ...]:
    parameters: list[FactoryTalkComponentParameter] = []
    for child in node:
        child_tag = local_name(child.tag).lower()
        if child_tag == "parameters":
            for parameter_node in child:
                parameter = parameter_from_node(parameter_node)
                if parameter is not None:
                    parameters.append(parameter)
        elif child_tag in {"parameter", "globalparameter"}:
            parameter = parameter_from_node(child)
            if parameter is not None:
                parameters.append(parameter)
    return tuple(parameters)


def parameter_from_node(node: ET.Element) -> FactoryTalkComponentParameter | None:
    tag = local_name(node.tag).lower()
    if tag not in {"parameter", "globalparameter"}:
        return None
    name = node.attrib.get("name", "")
    if not name:
        return None
    value = node.attrib.get("value", "")
    description = node.attrib.get("description", "")
    return FactoryTalkComponentParameter(
        name=name,
        value=value,
        description=description,
        tag_references=extract_references_from_values([name, value, description]),
        raw={"tag": local_name(node.tag), "attributes": dict(node.attrib)},
    )


def parse_global_object_link(attributes: dict[str, str]) -> FactoryTalkGlobalObjectLink | None:
    reference = global_object_reference(attributes)
    if not reference:
        return None
    return FactoryTalkGlobalObjectLink(
        reference=reference,
        link_file=attributes.get("linkFile", ""),
        link_object=attributes.get("linkObject", ""),
        link_base_object=attributes.get("linkBaseObject", ""),
        link_size=attributes.get("linkSize", ""),
        link_connections=attributes.get("linkConnections", ""),
        link_animations=attributes.get("linkAnimations", ""),
        link_tooltip_text=attributes.get("linkToolTipText", ""),
        raw={key: value for key, value in attributes.items() if key.startswith("link") or key == "isReferenceObject"},
    )


def parse_vba_links(node: ET.Element) -> tuple[FactoryTalkVbaLink, ...]:
    links: list[FactoryTalkVbaLink] = []
    expose_to_vba = node.attrib.get("exposeToVba", "")
    if expose_to_vba and expose_to_vba != "notExposed":
        links.append(vba_link_from_value("exposeToVba", expose_to_vba, {"attributes": {"exposeToVba": expose_to_vba}}))
    for key, value in node.attrib.items():
        if key == "exposeToVba":
            continue
        if "vba" in key.lower() or "macro" in key.lower() or "procedure" in key.lower():
            links.append(vba_link_from_value(key, value, {"attributes": {key: value}}))
    return tuple(links)


def vba_link_from_value(name: str, value: str, raw: dict[str, Any]) -> FactoryTalkVbaLink:
    return FactoryTalkVbaLink(name=name, value=value, tag_references=extract_hmi_tag_references(value), raw=raw)


def extract_references_from_values(values: list[str]) -> tuple[HmiTagReference, ...]:
    return merge_references(*(extract_hmi_tag_references(value) for value in values))


def merge_references(*reference_groups: tuple[HmiTagReference, ...]) -> tuple[HmiTagReference, ...]:
    references: list[HmiTagReference] = []
    seen: set[str] = set()
    for group in reference_groups:
        for reference in group:
            key = reference.original
            if key in seen:
                continue
            seen.add(key)
            references.append(reference)
    return tuple(references)


def parse_parameter_file(path: str | Path) -> FactoryTalkParameterFile:
    source_path = Path(path)
    text = read_text_fallback(source_path)
    parameters: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", ";", "'", "!", "@")):
            continue
        left, separator, right = stripped.partition("=")
        if not separator:
            left, separator, right = stripped.partition(",")
        if not separator:
            continue
        key = left.strip().lstrip("#")
        if not key.isdigit():
            continue
        parameters[f"p{int(key)}"] = right.strip()
    return FactoryTalkParameterFile(name=source_path.name, source_path=str(source_path), parameters=parameters)


def display_dimensions(root: ET.Element) -> tuple[float | None, float | None]:
    for node in root.iter():
        if local_name(node.tag) != "displaySettings":
            continue
        return float_or_none(node.attrib.get("width")), float_or_none(node.attrib.get("height"))
    return None, None


def references_from_subtree(node: ET.Element) -> tuple[HmiTagReference, ...]:
    references: list[HmiTagReference] = []
    seen: set[str] = set()
    for candidate in node.iter():
        values = list(candidate.attrib.values())
        if candidate.text:
            values.append(candidate.text)
        for value in values:
            for reference in extract_hmi_tag_references(value):
                key = reference.original
                if key in seen:
                    continue
                seen.add(key)
                references.append(reference)
    return tuple(references)


def is_component_node(tag: str, attributes: dict[str, str]) -> bool:
    if tag in NON_COMPONENT_TAGS:
        return False
    return tag == "group" or "left" in attributes or "top" in attributes or "linkBaseObject" in attributes


def is_global_instance_node(tag: str, attributes: dict[str, str]) -> bool:
    return tag.lower() == "globalobject" or "linkFile" in attributes or attributes.get("isReferenceObject") == "true" or "linkBaseObject" in attributes


def count_component_children(node: ET.Element) -> int:
    return sum(1 for child in list(node) if is_component_node(local_name(child.tag), child.attrib))


NON_COMPONENT_TAGS = {
    "gfx",
    "displaySettings",
    "color",
    "animations",
    "command",
    "connections",
    "states",
    "parameters",
    "animateVisibility",
    "animateColor",
    "state",
    "connection",
    "up",
    "down",
    "caption",
    "action",
    "animateFill",
    "animateWidth",
    "animateHeight",
    "animateHorizontalPosition",
    "animateVerticalPosition",
}


def bounds(attributes: dict[str, str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in ("left", "top", "width", "height"):
        value = float_or_none(attributes.get(key))
        if value is not None:
            result[key] = value
    return result


def has_complete_bounds(value: dict[str, float]) -> bool:
    return all(key in value for key in ("left", "top", "width", "height"))


def subtree_bounds(node: ET.Element) -> dict[str, float]:
    min_left = float("inf")
    min_top = float("inf")
    max_right = float("-inf")
    max_bottom = float("-inf")
    for child in node.iter():
        child_bounds = bounds(child.attrib)
        if not has_complete_bounds(child_bounds):
            continue
        left = child_bounds["left"]
        top = child_bounds["top"]
        width = child_bounds["width"]
        height = child_bounds["height"]
        min_left = min(min_left, left)
        min_top = min(min_top, top)
        max_right = max(max_right, left + width)
        max_bottom = max(max_bottom, top + height)
    if min_left == float("inf"):
        return {"left": 0.0, "top": 0.0, "width": 100.0, "height": 100.0}
    return {"left": min_left, "top": min_top, "width": max_right - min_left, "height": max_bottom - min_top}


def geometry(tag: str, attributes: dict[str, str], component_bounds: dict[str, float]) -> dict[str, Any]:
    if tag == "rectangle":
        return {"geometry_type": "rectangle", **component_bounds}
    if tag == "roundedRectangle":
        return {
            "geometry_type": "roundedRectangle",
            **component_bounds,
            "roundingWidth": float_or_zero(attributes.get("roundingWidth")),
            "roundingHeight": float_or_zero(attributes.get("roundingHeight")),
        }
    if tag == "ellipse":
        return {"geometry_type": "ellipse", **component_bounds}
    if tag == "line":
        coords = parse_float_list(attributes.get("line", ""))
        if len(coords) >= 4:
            return {"geometry_type": "line", "x1": coords[0], "y1": coords[1], "x2": coords[2], "y2": coords[3]}
        left = component_bounds.get("left", 0.0)
        top = component_bounds.get("top", 0.0)
        return {
            "geometry_type": "line",
            "x1": left,
            "y1": top,
            "x2": left + component_bounds.get("width", 0.0),
            "y2": top + component_bounds.get("height", 0.0),
        }
    if tag in {"polygon", "polyline"}:
        coords = parse_float_list(attributes.get("path", ""))
        points = [[coords[index], coords[index + 1]] for index in range(0, len(coords) - 1, 2)]
        if points:
            return {"geometry_type": tag, "points": points}
    return {"geometry_type": "bounds", **component_bounds} if component_bounds else {}


def global_object_reference(attributes: dict[str, str]) -> str:
    link_file = attributes.get("linkFile", "")
    link_object = attributes.get("linkObject", "")
    if link_file and link_object:
        return f"{link_file}/{link_object}"
    return attributes.get("linkBaseObject", "")


def component_key(parent_path: str, sibling_index: int, tag: str, name: str) -> str:
    segment = f"{sibling_index}:{safe_key(tag)}:{safe_key(name)}"
    return f"{parent_path}/{segment}" if parent_path else segment


def safe_key(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in str(value).strip())
    return cleaned.strip("_") or "unnamed"


def screen_type_for_path(path: Path) -> str:
    path_text = "/".join(part.lower() for part in path.parts)
    return "global_object" if "global" in path_text else "display"


def ignored_factorytalk_xml(path: Path) -> bool:
    name = path.name
    return "BatchImport_" in name or name == "DisplaysExport.txt"


def directory_sha256(path: Path, suffixes: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(candidate for candidate in path.rglob("*") if candidate.is_file() and candidate.suffix.lower() in suffixes):
        digest.update(str(file_path.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_text_fallback(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue
    return path.read_text(errors="ignore")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def float_or_zero(value: str | None) -> float:
    result = float_or_none(value)
    return 0.0 if result is None else result


def parse_float_list(value: str) -> list[float]:
    result: list[float] = []
    for part in str(value or "").replace(",", " ").split():
        number = float_or_none(part)
        if number is not None:
            result.append(number)
    return result
