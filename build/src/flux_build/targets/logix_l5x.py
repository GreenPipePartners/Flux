from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

from flux_mine.plc.models import PlcController, PlcDataType, PlcMember, PlcProgram, PlcProject, PlcTag


def build_logix_l5x(project: PlcProject) -> bytes:
    if len(project.controllers) != 1:
        raise ValueError("Generated L5X currently supports exactly one controller")

    controller = project.controllers[0]
    root = ET.Element(
        "RSLogix5000Content",
        {
            "SchemaRevision": "1.0",
            "SoftwareRevision": software_revision(controller),
            "TargetName": controller.name,
            "TargetType": "Controller",
            "ContainsContext": "false",
            "Owner": "Flux.build",
            "ExportDate": datetime.now(UTC).strftime("%a %b %d %H:%M:%S %Y"),
            "ExportOptions": "NoRawData L5KData DecoratedData",
        },
    )
    controller_node = ET.SubElement(root, "Controller", controller_attributes(controller))
    append_data_types(controller_node, controller.data_types)
    append_add_on_instructions(controller_node, controller.data_types)
    append_tags(controller_node, controller.tags)
    append_programs(controller_node, controller.programs)
    append_tasks(controller_node, controller)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def controller_attributes(controller: PlcController) -> dict[str, str]:
    attrs = clean_attrs(controller.raw)
    attrs.update({"Use": attrs.get("Use", "Target"), "Name": controller.name})
    if controller.processor_type:
        attrs["ProcessorType"] = controller.processor_type
    if controller.major_version is not None:
        attrs["MajorRev"] = str(controller.major_version)
    attrs.setdefault("MinorRev", "0")
    return attrs


def software_revision(controller: PlcController) -> str:
    major = controller.major_version if controller.major_version is not None else 1
    minor = str(controller.raw.get("MinorRev") or "0").strip() or "0"
    return f"{major}.{int_or_zero(minor):02d}"


def append_data_types(parent: ET.Element, data_types: tuple[PlcDataType, ...]) -> None:
    data_types_node = ET.SubElement(parent, "DataTypes")
    for data_type in data_types:
        if data_type.is_aoi:
            continue
        data_type_node = ET.SubElement(data_types_node, "DataType", {"Name": data_type.name, **clean_attrs(data_type.raw)})
        append_description(data_type_node, data_type.description)
        members_node = ET.SubElement(data_type_node, "Members")
        append_members(members_node, data_type.members, member_tag="Member")


def append_add_on_instructions(parent: ET.Element, data_types: tuple[PlcDataType, ...]) -> None:
    aoi_node = ET.SubElement(parent, "AddOnInstructionDefinitions")
    for data_type in data_types:
        if not data_type.is_aoi:
            continue
        definition_node = ET.SubElement(
            aoi_node,
            "AddOnInstructionDefinition",
            {"Name": data_type.name, **clean_attrs(data_type.raw)},
        )
        append_description(definition_node, data_type.description)
        parameters_node = ET.SubElement(definition_node, "Parameters")
        append_members(parameters_node, data_type.members, member_tag="Parameter")


def append_members(parent: ET.Element, members: tuple[PlcMember, ...], *, member_tag: str) -> None:
    for member in members:
        attrs = clean_attrs(member.raw)
        attrs.update({"Name": member.name, "DataType": member.data_type})
        if member.array_dimensions:
            attrs["Dimensions"] = dimensions_value(member.array_dimensions)
        if member.hidden:
            attrs["Hidden"] = "true"
        if member.target:
            attrs["Target"] = member.target
        if member.bit_number is not None:
            attrs["BitNumber"] = str(member.bit_number)
        if member.external_access:
            attrs["ExternalAccess"] = member.external_access
        if member.usage:
            attrs["Usage"] = member.usage
        if member.required is not None:
            attrs["Required"] = bool_value(member.required)
        if member.visible is not None:
            attrs["Visible"] = bool_value(member.visible)
        if member.constant is not None:
            attrs["Constant"] = bool_value(member.constant)
        if member.radix:
            attrs["Radix"] = member.radix
        member_node = ET.SubElement(parent, member_tag, attrs)
        append_description(member_node, member.description)


def append_tags(parent: ET.Element, tags: tuple[PlcTag, ...]) -> None:
    tags_node = ET.SubElement(parent, "Tags")
    for tag in tags:
        append_tag(tags_node, tag)


def append_tag(parent: ET.Element, tag: PlcTag) -> None:
    attrs = clean_attrs(tag.raw, exclude={"data"})
    attrs.update({"Name": tag.name, "TagType": tag.tag_type, "DataType": tag.data_type})
    if tag.array_dimensions:
        attrs["Dimensions"] = dimensions_value(tag.array_dimensions)
    if tag.alias_for:
        attrs["AliasFor"] = tag.alias_for
    if tag.hidden:
        attrs["Hidden"] = "true"
    if tag.external_access:
        attrs["ExternalAccess"] = tag.external_access
    if tag.constant is not None:
        attrs["Constant"] = bool_value(tag.constant)
    if tag.radix:
        attrs["Radix"] = tag.radix
    tag_node = ET.SubElement(parent, "Tag", attrs)
    append_description(tag_node, tag.description)
    for payload in tag.raw.get("data", []):
        append_tag_data(tag_node, payload)


def append_tag_data(parent: ET.Element, payload: dict[str, Any]) -> None:
    attrs = clean_attrs(payload.get("attributes") or {})
    if payload.get("format"):
        attrs["Format"] = str(payload["format"])
    data_node = ET.SubElement(parent, "Data", attrs)
    if payload.get("text"):
        data_node.text = str(payload["text"])
    for child_xml in payload.get("children", []):
        data_node.append(ET.fromstring(str(child_xml)))


def append_programs(parent: ET.Element, programs: tuple[PlcProgram, ...]) -> None:
    programs_node = ET.SubElement(parent, "Programs")
    for program in programs:
        attrs = clean_attrs(program.raw)
        attrs.update({"Name": program.name})
        if program.main_routine_name:
            attrs["MainRoutineName"] = program.main_routine_name
        attrs.setdefault("Disabled", "false")
        attrs.setdefault("UseAsFolder", "false")
        program_node = ET.SubElement(programs_node, "Program", attrs)
        append_tags(program_node, program.tags)
        routines_node = ET.SubElement(program_node, "Routines")
        for routine in program.routines:
            routine_node = ET.SubElement(
                routines_node,
                "Routine",
                {"Name": routine.name, "Type": routine.routine_type or "RLL", **clean_attrs(routine.raw)},
            )
            rll_node = ET.SubElement(routine_node, "RLLContent")
            for rung in routine.rungs:
                rung_node = ET.SubElement(
                    rll_node,
                    "Rung",
                    {"Number": str(rung.number), "Type": rung.rung_type or "N", **clean_attrs(rung.raw)},
                )
                text_node = ET.SubElement(rung_node, "Text")
                text_node.text = rung.text


def append_tasks(parent: ET.Element, controller: PlcController) -> None:
    tasks_node = ET.SubElement(parent, "Tasks")
    for task in controller.tasks:
        attrs = clean_attrs(task.raw)
        attrs.update({"Name": task.name})
        if task.task_type:
            attrs["Type"] = task.task_type
        if task.priority is not None:
            attrs["Priority"] = str(task.priority)
        if task.rate is not None:
            attrs["Rate"] = str(task.rate)
        if task.watchdog is not None:
            attrs["Watchdog"] = str(task.watchdog)
        if task.disable_update_outputs is not None:
            attrs["DisableUpdateOutputs"] = bool_value(task.disable_update_outputs)
        if task.inhibit_task is not None:
            attrs["InhibitTask"] = bool_value(task.inhibit_task)
        task_node = ET.SubElement(tasks_node, "Task", attrs)
        scheduled_node = ET.SubElement(task_node, "ScheduledPrograms")
        for program_name in task.scheduled_programs:
            ET.SubElement(scheduled_node, "ScheduledProgram", {"Name": program_name})


def append_description(parent: ET.Element, description: str) -> None:
    if not description:
        return
    node = ET.SubElement(parent, "Description")
    node.text = description


def clean_attrs(attrs: dict[str, Any], *, exclude: set[str] | None = None) -> dict[str, str]:
    exclude = {"source", *(exclude or set())}
    result: dict[str, str] = {}
    for key, value in attrs.items():
        if key in exclude or value is None or isinstance(value, (dict, list, tuple)):
            continue
        result[str(key)] = str(value)
    return result


def dimensions_value(dimensions: tuple[int, ...]) -> str:
    return ",".join(str(dimension) for dimension in dimensions)


def bool_value(value: bool) -> str:
    return "true" if value else "false"


def int_or_zero(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
