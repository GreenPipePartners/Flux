from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from flux_mine.plc.models import (
    PlcController,
    PlcDataType,
    PlcMember,
    PlcProgram,
    PlcProject,
    PlcTag,
    parse_dimensions,
)


def parse_l5x_file(path: str | Path) -> PlcProject:
    source_path = Path(path)
    content = source_path.read_bytes()
    return parse_l5x_text(
        content.decode("utf-8-sig", errors="replace"),
        source_path=str(source_path),
        source_sha256=hashlib.sha256(content).hexdigest(),
    )


def parse_l5x_text(text: str, *, source_path: str = "", source_sha256: str = "") -> PlcProject:
    root = ET.fromstring(text)
    controller_node = child(root, "Controller")
    if controller_node is None:
        raise ValueError("L5X file does not contain a Controller element")

    controller = parse_controller(controller_node, source_path=source_path)
    return PlcProject(controllers=(controller,), source_path=source_path, source_sha256=source_sha256)


def parse_controller(node: ET.Element, *, source_path: str = "") -> PlcController:
    data_types = tuple(parse_data_types(child(node, "DataTypes")))
    data_types += tuple(parse_add_on_instructions(child(node, "AddOnInstructionDefinitions")))
    tags = tuple(parse_tags(child(node, "Tags"), scope="Global"))
    programs = tuple(parse_programs(child(node, "Programs")))
    major_version = int_or_none(node.attrib.get("MajorRev"))
    return PlcController(
        name=node.attrib.get("Name", "Unknown"),
        processor_type=node.attrib.get("ProcessorType", ""),
        major_version=major_version,
        comm_path=node.attrib.get("CommPath", ""),
        data_types=data_types,
        tags=tags,
        programs=programs,
        source_path=source_path,
        raw=dict(node.attrib),
    )


def parse_data_types(node: ET.Element | None) -> list[PlcDataType]:
    if node is None:
        return []
    result: list[PlcDataType] = []
    for data_type_node in children(node, "DataType"):
        name = data_type_node.attrib.get("Name")
        if not name:
            continue
        members_node = child(data_type_node, "Members")
        result.append(
            PlcDataType(
                name=name,
                description=description(data_type_node),
                is_aoi=False,
                members=tuple(parse_members(members_node, member_tag="Member")),
                raw=dict(data_type_node.attrib),
            )
        )
    return result


def parse_add_on_instructions(node: ET.Element | None) -> list[PlcDataType]:
    if node is None:
        return []
    result: list[PlcDataType] = []
    for aoi_node in children(node, "AddOnInstructionDefinition"):
        name = aoi_node.attrib.get("Name")
        if not name:
            continue
        members: list[PlcMember] = []
        members.extend(parse_members(child(aoi_node, "Parameters"), member_tag="Parameter"))
        members.extend(parse_members(child(aoi_node, "LocalTags"), member_tag="LocalTag"))
        result.append(
            PlcDataType(
                name=name,
                description=description(aoi_node),
                is_aoi=True,
                members=tuple(members),
                raw=dict(aoi_node.attrib),
            )
        )
    return result


def parse_members(node: ET.Element | None, *, member_tag: str) -> list[PlcMember]:
    if node is None:
        return []
    result: list[PlcMember] = []
    for member_node in children(node, member_tag):
        name = member_node.attrib.get("Name")
        data_type = member_node.attrib.get("DataType")
        if not name or not data_type:
            continue
        result.append(
            PlcMember(
                name=name,
                data_type=data_type,
                array_dimensions=dimensions_from_attrs(member_node.attrib),
                hidden=bool_attr(member_node.attrib.get("Hidden")),
                description=description(member_node),
                target=member_node.attrib.get("Target", ""),
                bit_number=int_or_none(member_node.attrib.get("BitNumber")),
                external_access=member_node.attrib.get("ExternalAccess", ""),
                usage=member_node.attrib.get("Usage", ""),
                required=optional_bool_attr(member_node.attrib.get("Required")),
                visible=optional_bool_attr(member_node.attrib.get("Visible")),
                constant=optional_bool_attr(member_node.attrib.get("Constant")),
                radix=member_node.attrib.get("Radix", ""),
                raw=dict(member_node.attrib),
            )
        )
    return result


def parse_programs(node: ET.Element | None) -> list[PlcProgram]:
    if node is None:
        return []
    result: list[PlcProgram] = []
    for program_node in children(node, "Program"):
        name = program_node.attrib.get("Name")
        if not name:
            continue
        result.append(
            PlcProgram(
                name=name,
                tags=tuple(parse_tags(child(program_node, "Tags"), scope=name)),
                raw=dict(program_node.attrib),
            )
        )
    return result


def parse_tags(node: ET.Element | None, *, scope: str) -> list[PlcTag]:
    if node is None:
        return []
    result: list[PlcTag] = []
    for tag_node in children(node, "Tag"):
        name = tag_node.attrib.get("Name")
        if not name:
            continue
        tag_type = tag_node.attrib.get("TagType", "Base")
        alias_for = tag_node.attrib.get("AliasFor", "")
        result.append(
            PlcTag(
                name=name,
                data_type=tag_node.attrib.get("DataType", "ALIAS" if alias_for else "UNKNOWN"),
                scope=scope,
                tag_type=tag_type,
                array_dimensions=dimensions_from_attrs(tag_node.attrib),
                alias_for=alias_for,
                hidden=bool_attr(tag_node.attrib.get("Hidden")),
                description=description(tag_node),
                external_access=tag_node.attrib.get("ExternalAccess", ""),
                constant=optional_bool_attr(tag_node.attrib.get("Constant")),
                radix=tag_node.attrib.get("Radix", ""),
                raw=dict(tag_node.attrib),
            )
        )
    return result


def dimensions_from_attrs(attrs: dict[str, str]) -> tuple[int, ...]:
    return parse_dimensions(attrs.get("Dimensions") or attrs.get("Dimension"))


def description(node: ET.Element) -> str:
    description_node = child(node, "Description")
    if description_node is None or description_node.text is None:
        return ""
    return description_node.text.strip()


def child(node: ET.Element, name: str) -> ET.Element | None:
    for candidate in node:
        if local_name(candidate.tag) == name:
            return candidate
    return None


def children(node: ET.Element, name: str) -> list[ET.Element]:
    return [candidate for candidate in node if local_name(candidate.tag) == name]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def bool_attr(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def optional_bool_attr(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return bool_attr(value)


def int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None
