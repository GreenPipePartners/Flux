from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flux_mine.hmi.tag_refs import HmiTagReference, extract_hmi_tag_references


@dataclass(frozen=True)
class FactoryTalkComponent:
    name: str
    component_type: str
    attributes: dict[str, str] = field(default_factory=dict)
    bounds: dict[str, float] = field(default_factory=dict)
    global_object_reference: str = ""
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
    for node in root.iter():
        tag = local_name(node.tag)
        if not is_component_node(tag, node.attrib):
            continue
        references = references_from_subtree(node)
        components.append(
            FactoryTalkComponent(
                name=node.attrib.get("name", f"Unnamed_{tag}"),
                component_type=tag,
                attributes={key: value for key, value in node.attrib.items()},
                bounds=bounds(node.attrib),
                global_object_reference=global_object_reference(node.attrib),
                tag_references=references,
                raw={"tag": tag, "attributes": dict(node.attrib)},
            )
        )
    return FactoryTalkScreen(
        name=name,
        screen_type=screen_type,
        source_path=source_path,
        width=width,
        height=height,
        components=tuple(components),
    )


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


def global_object_reference(attributes: dict[str, str]) -> str:
    link_file = attributes.get("linkFile", "")
    link_object = attributes.get("linkObject", "")
    if link_file and link_object:
        return f"{link_file}/{link_object}"
    return attributes.get("linkBaseObject", "")


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
