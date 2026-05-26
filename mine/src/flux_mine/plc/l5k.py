from __future__ import annotations

import hashlib
import re
from pathlib import Path

from flux_mine.plc.models import (
    PlcController,
    PlcDataType,
    PlcMember,
    PlcProgram,
    PlcProject,
    PlcRoutine,
    PlcRung,
    PlcTask,
    PlcTag,
    parse_dimensions,
    parse_rll_instructions,
)


IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
DATA_TYPE = r"[A-Za-z_][A-Za-z0-9_:]*"

CONTROLLER_RE = re.compile(rf"^CONTROLLER\s+(?P<name>{IDENTIFIER})\b(?P<tail>.*)")
DATATYPE_RE = re.compile(rf"^DATATYPE\s+(?P<name>{IDENTIFIER})\b(?P<tail>.*)")
AOI_RE = re.compile(rf"^ADD_ON_INSTRUCTION_DEFINITION\s+(?P<name>{IDENTIFIER})\b(?P<tail>.*)")
PROGRAM_RE = re.compile(rf"^PROGRAM\s+(?P<name>{IDENTIFIER})\b(?P<tail>.*)")
TASK_RE = re.compile(rf"^TASK\s+(?P<name>{IDENTIFIER})\b(?P<tail>.*)")
ROUTINE_RE = re.compile(rf"^ROUTINE\s+(?P<name>{IDENTIFIER})\b(?P<tail>.*)")
RUNG_RE = re.compile(r"^(?P<type>[A-Za-z]+)\s*:\s*(?P<text>.*)$")
SCHEDULED_PROGRAM_RE = re.compile(rf"^(?P<name>{IDENTIFIER})\s*;?$")
ALIAS_RE = re.compile(rf"^(?P<name>{IDENTIFIER})\s+OF\s+(?P<base>[^\s(;]+)(?P<tail>.*)$")
COLON_DECL_RE = re.compile(
    rf"^(?P<name>{IDENTIFIER})\s*:\s*(?P<data_type>{DATA_TYPE})(?P<array>\[[\d,\s]+\])?(?P<tail>.*)$"
)
TYPE_FIRST_DECL_RE = re.compile(
    rf"^(?P<data_type>{DATA_TYPE})\s+(?P<name>{IDENTIFIER})(?P<array>\[[\d,\s]+\])?(?P<tail>.*)$"
)
PROPERTY_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:=\s*(?:\"(?P<quoted>(?:[^\"\\]|\\.)*)\"|(?P<bare>[^,)]+))"
)


def parse_l5k_file(path: str | Path) -> PlcProject:
    source_path = Path(path)
    content = source_path.read_bytes()
    return parse_l5k_text(
        content.decode("utf-8-sig", errors="replace"),
        source_path=str(source_path),
        source_sha256=hashlib.sha256(content).hexdigest(),
    )


def parse_l5k_text(text: str, *, source_path: str = "", source_sha256: str = "") -> PlcProject:
    parser = L5KTextParser(source_path=source_path)
    return PlcProject(
        controllers=(parser.parse(text),),
        source_path=source_path,
        source_sha256=source_sha256,
    )


class L5KTextParser:
    def __init__(self, *, source_path: str = "") -> None:
        self.source_path = source_path
        self.controller_name = "Unknown"
        self.processor_type = ""
        self.major_version: int | None = None
        self.comm_path = ""
        self.controller_raw: dict[str, str] = {}
        self.data_types: list[PlcDataType] = []
        self.global_tags: list[PlcTag] = []
        self.programs: list[PlcProgram] = []
        self.tasks: list[PlcTask] = []

        self.state = "global"
        self.current_type_name = ""
        self.current_type_description = ""
        self.current_type_is_aoi = False
        self.current_type_raw: dict[str, str] = {}
        self.current_members: list[PlcMember] = []
        self.current_program_name = ""
        self.current_program_main_routine_name = ""
        self.current_program_raw: dict[str, str] = {}
        self.current_program_tags: list[PlcTag] = []
        self.current_program_routines: list[PlcRoutine] = []
        self.current_routine_name = ""
        self.current_routine_type = ""
        self.current_routine_raw: dict[str, str] = {}
        self.current_rungs: list[PlcRung] = []
        self.current_task_name = ""
        self.current_task_raw: dict[str, str] = {}
        self.current_task_scheduled_programs: list[str] = []
        self.current_tag_scope = "Global"

    def parse(self, text: str) -> PlcController:
        for raw_line in text.splitlines():
            line = clean_line(raw_line)
            if not line:
                continue
            self.consume(line)
        if self.state == "datatype":
            self.close_data_type()
        if self.state == "program" or self.current_program_name:
            self.close_program()
        if self.state == "task" or self.current_task_name:
            self.close_task()
        if self.controller_name == "Unknown":
            raise ValueError("L5K file does not contain a CONTROLLER definition")
        return PlcController(
            name=self.controller_name,
            processor_type=self.processor_type,
            major_version=self.major_version,
            comm_path=self.comm_path,
            data_types=tuple(self.data_types),
            tags=tuple(self.global_tags),
            programs=tuple(self.programs),
            tasks=tuple(self.tasks),
            source_path=self.source_path,
            raw=self.controller_raw,
        )

    def consume(self, line: str) -> None:
        if self.state == "global":
            self.consume_global(line)
        elif self.state == "controller":
            self.consume_controller(line)
        elif self.state == "datatype":
            self.consume_data_type(line)
        elif self.state == "aoi":
            self.consume_aoi(line)
        elif self.state == "program":
            self.consume_program(line)
        elif self.state == "routine":
            self.consume_routine(line)
        elif self.state == "task":
            self.consume_task(line)
        elif self.state == "tags":
            self.consume_tags(line)

    def consume_global(self, line: str) -> None:
        match = CONTROLLER_RE.match(line)
        if match is None:
            return
        self.controller_name = match.group("name")
        self.apply_controller_properties(parse_properties(match.group("tail")))
        self.state = "controller"

    def consume_controller(self, line: str) -> None:
        self.apply_controller_properties(parse_properties(line))

        data_type_match = DATATYPE_RE.match(line)
        if data_type_match is not None:
            self.open_data_type(data_type_match.group("name"), data_type_match.group("tail"), is_aoi=False)
            return

        aoi_match = AOI_RE.match(line)
        if aoi_match is not None:
            self.open_data_type(aoi_match.group("name"), aoi_match.group("tail"), is_aoi=True)
            self.state = "aoi"
            return

        program_match = PROGRAM_RE.match(line)
        if program_match is not None:
            properties = parse_properties(program_match.group("tail"))
            self.current_program_name = program_match.group("name")
            self.current_program_main_routine_name = properties.get("MAIN", properties.get("MainRoutineName", ""))
            self.current_program_raw = properties
            self.current_program_tags = []
            self.current_program_routines = []
            self.state = "program"
            return

        task_match = TASK_RE.match(line)
        if task_match is not None:
            self.current_task_name = task_match.group("name")
            self.current_task_raw = parse_properties(task_match.group("tail"))
            self.current_task_scheduled_programs = []
            self.state = "task"
            return

        if keyword(line) == "TAG":
            self.current_tag_scope = "Global"
            self.state = "tags"

    def consume_data_type(self, line: str) -> None:
        if keyword(line) == "END_DATATYPE":
            self.close_data_type()
            self.state = "controller"
            return
        if self.consume_type_description(line):
            return
        member = parse_member(line)
        if member is not None:
            self.current_members.append(member)

    def consume_aoi(self, line: str) -> None:
        if keyword(line) == "END_ADD_ON_INSTRUCTION_DEFINITION":
            self.close_data_type()
            self.state = "controller"
            return
        if keyword(line) in {"LOCAL_TAGS", "END_LOCAL_TAGS", "PARAMETERS", "END_PARAMETERS"}:
            return
        if self.consume_type_description(line):
            return
        member = parse_member(line)
        if member is not None:
            self.current_members.append(member)

    def consume_program(self, line: str) -> None:
        if keyword(line) == "END_PROGRAM":
            self.close_program()
            self.state = "controller"
            return
        if keyword(line) == "TAG":
            self.current_tag_scope = self.current_program_name
            self.state = "tags"
            return
        if keyword(line) in {"CHILD_PROGRAMS", "END_CHILD_PROGRAMS"}:
            return
        routine_match = ROUTINE_RE.match(line)
        if routine_match is not None:
            self.current_routine_name = routine_match.group("name")
            self.current_routine_type = "RLL"
            self.current_routine_raw = parse_properties(routine_match.group("tail"))
            self.current_rungs = []
            self.state = "routine"
            return
        self.current_program_raw.update(parse_properties(line))

    def consume_routine(self, line: str) -> None:
        if keyword(line) == "END_ROUTINE":
            self.close_routine()
            self.state = "program"
            return
        rung = parse_rung(line, number=len(self.current_rungs))
        if rung is not None:
            self.current_rungs.append(rung)

    def consume_task(self, line: str) -> None:
        if keyword(line) == "END_TASK":
            self.close_task()
            self.state = "controller"
            return
        self.current_task_raw.update(parse_properties(line))
        scheduled_match = SCHEDULED_PROGRAM_RE.match(strip_declaration(line))
        if scheduled_match is not None:
            self.current_task_scheduled_programs.append(scheduled_match.group("name"))

    def consume_tags(self, line: str) -> None:
        if keyword(line) == "END_TAG":
            self.state = "controller" if self.current_tag_scope == "Global" else "program"
            return
        tag = parse_tag(line, scope=self.current_tag_scope)
        if tag is None:
            return
        if self.current_tag_scope == "Global":
            self.global_tags.append(tag)
        else:
            self.current_program_tags.append(tag)

    def apply_controller_properties(self, properties: dict[str, str]) -> None:
        if not properties:
            return
        self.controller_raw.update(properties)
        self.processor_type = properties.get("ProcessorType", self.processor_type)
        self.comm_path = properties.get("CommPath", self.comm_path)
        if "Major" in properties:
            self.major_version = int_or_none(properties["Major"])
        if "MajorRev" in properties:
            self.major_version = int_or_none(properties["MajorRev"])

    def open_data_type(self, name: str, tail: str, *, is_aoi: bool) -> None:
        properties = parse_properties(tail)
        self.current_type_name = name
        self.current_type_description = properties.get("Description", "")
        self.current_type_is_aoi = is_aoi
        self.current_type_raw = properties
        self.current_members = []
        self.state = "aoi" if is_aoi else "datatype"

    def consume_type_description(self, line: str) -> bool:
        properties = parse_properties(line)
        if "Description" not in properties or declaration_like(line):
            return False
        self.current_type_description = properties["Description"]
        self.current_type_raw.update(properties)
        return True

    def close_data_type(self) -> None:
        if not self.current_type_name:
            return
        self.data_types.append(
            PlcDataType(
                name=self.current_type_name,
                description=self.current_type_description,
                is_aoi=self.current_type_is_aoi,
                members=tuple(self.current_members),
                raw=self.current_type_raw,
            )
        )
        self.current_type_name = ""
        self.current_type_description = ""
        self.current_type_is_aoi = False
        self.current_type_raw = {}
        self.current_members = []

    def close_program(self) -> None:
        if not self.current_program_name:
            return
        self.programs.append(
            PlcProgram(
                name=self.current_program_name,
                main_routine_name=self.current_program_main_routine_name,
                tags=tuple(self.current_program_tags),
                routines=tuple(self.current_program_routines),
                raw=self.current_program_raw,
            )
        )
        self.current_program_name = ""
        self.current_program_main_routine_name = ""
        self.current_program_raw = {}
        self.current_program_tags = []
        self.current_program_routines = []

    def close_routine(self) -> None:
        if not self.current_routine_name:
            return
        self.current_program_routines.append(
            PlcRoutine(
                name=self.current_routine_name,
                routine_type=self.current_routine_type,
                rungs=tuple(self.current_rungs),
                raw=self.current_routine_raw,
            )
        )
        self.current_routine_name = ""
        self.current_routine_type = ""
        self.current_routine_raw = {}
        self.current_rungs = []

    def close_task(self) -> None:
        if not self.current_task_name:
            return
        self.tasks.append(
            PlcTask(
                name=self.current_task_name,
                task_type=self.current_task_raw.get("Type", ""),
                priority=int_or_none(self.current_task_raw.get("Priority")),
                rate=int_or_none(self.current_task_raw.get("Rate")),
                watchdog=int_or_none(self.current_task_raw.get("Watchdog")),
                disable_update_outputs=optional_bool_property(self.current_task_raw.get("DisableUpdateOutputs")),
                inhibit_task=optional_bool_property(self.current_task_raw.get("InhibitTask")),
                scheduled_programs=tuple(self.current_task_scheduled_programs),
                raw=self.current_task_raw,
            )
        )
        self.current_task_name = ""
        self.current_task_raw = {}
        self.current_task_scheduled_programs = []


def parse_rung(line: str, *, number: int) -> PlcRung | None:
    match = RUNG_RE.match(strip_declaration(line))
    if match is None:
        return None
    return PlcRung(
        number=number,
        rung_type=match.group("type"),
        text=match.group("text").strip(),
        instructions=parse_rll_instructions(match.group("text")),
        raw={"source": line},
    )


def parse_member(line: str) -> PlcMember | None:
    match = declaration_match(line)
    if match is None:
        return None
    properties = parse_properties(line)
    return PlcMember(
        name=match.group("name"),
        data_type=match.group("data_type"),
        array_dimensions=parse_dimensions(match.group("array")),
        hidden=bool_property(properties.get("Hidden")),
        description=properties.get("Description", ""),
        external_access=properties.get("ExternalAccess", ""),
        constant=optional_bool_property(properties.get("Constant")),
        radix=properties.get("Radix", ""),
        raw={"source": line, **properties},
    )


def parse_tag(line: str, *, scope: str) -> PlcTag | None:
    stripped = strip_declaration(line)
    alias_match = ALIAS_RE.match(stripped)
    properties = parse_properties(line)
    if alias_match is not None:
        return PlcTag(
            name=alias_match.group("name"),
            data_type="ALIAS",
            scope=scope,
            tag_type="Alias",
            alias_for=alias_match.group("base"),
            hidden=bool_property(properties.get("Hidden")),
            description=properties.get("Description", ""),
            external_access=properties.get("ExternalAccess", ""),
            constant=optional_bool_property(properties.get("Constant")),
            radix=properties.get("Radix", ""),
            raw={"source": line, **properties},
        )

    match = declaration_match(line)
    if match is None:
        return None
    return PlcTag(
        name=match.group("name"),
        data_type=match.group("data_type"),
        scope=scope,
        tag_type="Base",
        array_dimensions=parse_dimensions(match.group("array")),
        hidden=bool_property(properties.get("Hidden")),
        description=properties.get("Description", ""),
        external_access=properties.get("ExternalAccess", ""),
        constant=optional_bool_property(properties.get("Constant")),
        radix=properties.get("Radix", ""),
        raw={"source": line, **properties},
    )


def declaration_match(line: str) -> re.Match[str] | None:
    stripped = strip_declaration(line)
    if ignored_declaration(stripped):
        return None
    return COLON_DECL_RE.match(stripped) or TYPE_FIRST_DECL_RE.match(stripped)


def parse_properties(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in PROPERTY_RE.finditer(text):
        value = match.group("quoted") if match.group("quoted") is not None else match.group("bare")
        result[match.group("key")] = clean_property_value(value)
    return result


def clean_property_value(value: str) -> str:
    return value.strip().rstrip(";").rstrip(")").strip().replace('\\"', '"')


def clean_line(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith("//") or stripped.startswith("COMMENT"):
        return ""
    return stripped


def strip_declaration(line: str) -> str:
    return line.strip().rstrip(";").rstrip(",").strip()


def ignored_declaration(line: str) -> bool:
    normalized = keyword(line)
    return (
        not line
        or line.startswith("//")
        or line.startswith("COMMENT")
        or normalized.startswith("END_")
        or normalized in {"TAG", "LOCAL_TAGS", "PARAMETERS"}
    )


def declaration_like(line: str) -> bool:
    return declaration_match(line) is not None or ALIAS_RE.match(strip_declaration(line)) is not None


def keyword(line: str) -> str:
    return strip_declaration(line).upper()


def bool_property(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def optional_bool_property(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return bool_property(value)


def int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None
