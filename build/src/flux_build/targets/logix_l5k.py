from __future__ import annotations

import re
from typing import Any

from flux_mine.plc.models import PlcController, PlcDataType, PlcMember, PlcProgram, PlcProject, PlcTag


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_logix_l5k(project: PlcProject) -> bytes:
    if len(project.controllers) != 1:
        raise ValueError("Generated L5K currently supports exactly one controller")

    controller = project.controllers[0]
    lines: list[str] = ["IE_VER := 2.28;", "", controller_line(controller)]
    append_data_types(lines, controller.data_types)
    append_tags(lines, controller.tags, indent="\t")
    for program in controller.programs:
        append_program(lines, program)
    for task in controller.tasks:
        append_task(lines, task)
    lines.append("END_CONTROLLER")
    return ("\n".join(lines) + "\n").encode("utf-8")


def controller_line(controller: PlcController) -> str:
    properties: list[str] = []
    if controller.processor_type:
        properties.append(property_value("ProcessorType", controller.processor_type, quote=True))
    if controller.major_version is not None:
        properties.append(property_value("Major", controller.major_version))
    if controller.comm_path:
        properties.append(property_value("CommPath", controller.comm_path, quote=True))
    if not properties:
        return f"CONTROLLER {identifier(controller.name)}"
    return f"CONTROLLER {identifier(controller.name)} ({', '.join(properties)})"


def append_data_types(lines: list[str], data_types: tuple[PlcDataType, ...]) -> None:
    for data_type in data_types:
        if data_type.is_aoi:
            append_add_on_instruction(lines, data_type)
            continue
        lines.append("")
        lines.append(f"\tDATATYPE {identifier(data_type.name)}")
        for member in data_type.members:
            lines.append(member_line(member, indent="\t\t"))
        lines.append("\tEND_DATATYPE")


def append_add_on_instruction(lines: list[str], data_type: PlcDataType) -> None:
    lines.append("")
    lines.append(f"\tADD_ON_INSTRUCTION_DEFINITION {identifier(data_type.name)}")
    lines.append("\t\tPARAMETERS")
    for member in data_type.members:
        lines.append(member_line(member, indent="\t\t\t"))
    lines.append("\t\tEND_PARAMETERS")
    lines.append("\tEND_ADD_ON_INSTRUCTION_DEFINITION")


def member_line(member: PlcMember, *, indent: str) -> str:
    array = array_suffix(member.array_dimensions)
    properties = member_properties(member)
    return f"{indent}{identifier(member.name)} : {member.data_type}{array}{properties};"


def member_properties(member: PlcMember) -> str:
    properties: list[str] = []
    if member.description:
        properties.append(property_value("Description", member.description, quote=True))
    if member.hidden:
        properties.append(property_value("Hidden", 1))
    if member.radix:
        properties.append(property_value("RADIX", member.radix))
    return f" ({', '.join(properties)})" if properties else ""


def append_tags(lines: list[str], tags: tuple[PlcTag, ...], *, indent: str) -> None:
    lines.append("")
    lines.append(f"{indent}TAG")
    for tag in tags:
        lines.append(tag_line(tag, indent=f"{indent}\t"))
    lines.append(f"{indent}END_TAG")


def tag_line(tag: PlcTag, *, indent: str) -> str:
    if tag.tag_type.lower() == "alias" or tag.alias_for:
        return f"{indent}{identifier(tag.name)} OF {tag.alias_for};"
    array = array_suffix(tag.array_dimensions)
    properties = tag_properties(tag)
    initializer = tag_initializer(tag)
    return f"{indent}{identifier(tag.name)} : {tag.data_type}{array}{properties}{initializer};"


def tag_properties(tag: PlcTag) -> str:
    properties: list[str] = []
    if tag.description:
        properties.append(property_value("Description", tag.description, quote=True))
    if tag.hidden:
        properties.append(property_value("Hidden", 1))
    if tag.radix:
        properties.append(property_value("RADIX", tag.radix))
    return f" ({', '.join(properties)})" if properties else ""


def tag_initializer(tag: PlcTag) -> str:
    for payload in tag.raw.get("data", []):
        if str(payload.get("format", "")).lower() != "l5k":
            continue
        text = one_line(payload.get("text", ""))
        if text:
            return f" := {text}"
    return ""


def append_program(lines: list[str], program: PlcProgram) -> None:
    properties: list[str] = []
    if program.main_routine_name:
        properties.append(property_value("MAIN", program.main_routine_name, quote=True))
    properties.append(property_value("DisableFlag", 0))
    properties.append(property_value("UseAsFolder", 0))
    lines.append("")
    lines.append(f"\tPROGRAM {identifier(program.name)} ({', '.join(properties)})")
    append_tags(lines, program.tags, indent="\t\t")
    for routine in program.routines:
        lines.append("")
        lines.append(f"\t\tROUTINE {identifier(routine.name)}")
        for rung in routine.rungs:
            rung_type = rung.rung_type or "N"
            lines.append(f"\t\t\t{rung_type}: {rung.text}")
        lines.append("\t\tEND_ROUTINE")
    lines.append("\tEND_PROGRAM")


def append_task(lines: list[str], task: Any) -> None:
    properties: list[str] = []
    if task.task_type:
        properties.append(property_value("Type", task.task_type))
    if task.rate is not None:
        properties.append(property_value("Rate", task.rate))
    if task.priority is not None:
        properties.append(property_value("Priority", task.priority))
    if task.watchdog is not None:
        properties.append(property_value("Watchdog", task.watchdog))
    if task.disable_update_outputs is not None:
        properties.append(property_value("DisableUpdateOutputs", yes_no(task.disable_update_outputs)))
    if task.inhibit_task is not None:
        properties.append(property_value("InhibitTask", yes_no(task.inhibit_task)))
    lines.append("")
    lines.append(f"\tTASK {identifier(task.name)} ({', '.join(properties)})")
    for program_name in task.scheduled_programs:
        lines.append(f"\t\t{identifier(program_name)};")
    lines.append("\tEND_TASK")


def property_value(name: str, value: object, *, quote: bool = False) -> str:
    if quote:
        return f'{name} := "{escape_string(str(value))}"'
    return f"{name} := {value}"


def identifier(value: str) -> str:
    if not IDENTIFIER_RE.match(value):
        raise ValueError(f"Unsupported L5K identifier: {value}")
    return value


def array_suffix(dimensions: tuple[int, ...]) -> str:
    if not dimensions:
        return ""
    return "[" + ",".join(str(dimension) for dimension in dimensions) + "]"


def one_line(value: object) -> str:
    return " ".join(str(value).split())


def escape_string(value: str) -> str:
    return value.replace('"', '\\"')


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"
