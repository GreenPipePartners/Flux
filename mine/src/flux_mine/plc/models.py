from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


INSTRUCTION_RE = re.compile(r"\b(?P<mnemonic>XIO|XIC|TON|OTL|OTU|COP|JSR)\s*\((?P<operands>[^()]*)\)")
TAG_OPERAND_RE = re.compile(r"^(?P<base>[A-Za-z_][A-Za-z0-9_]*)(?P<member>(?:\.|\[).*)?$")

REFERENCE_ROLES: dict[str, tuple[str, ...]] = {
    "XIO": ("read",),
    "XIC": ("read",),
    "TON": ("timer",),
    "OTL": ("write",),
    "OTU": ("write",),
    "COP": ("source", "destination", "count"),
    "JSR": ("routine", "count"),
}


@dataclass(frozen=True)
class PlcMember:
    name: str
    data_type: str
    array_dimensions: tuple[int, ...] = ()
    hidden: bool = False
    description: str = ""
    target: str = ""
    bit_number: int | None = None
    external_access: str = ""
    usage: str = ""
    required: bool | None = None
    visible: bool | None = None
    constant: bool | None = None
    radix: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_packed_bit(self) -> bool:
        return self.data_type.upper() == "BIT" and bool(self.target) and self.bit_number is not None


@dataclass(frozen=True)
class PlcDataType:
    name: str
    description: str = ""
    is_aoi: bool = False
    members: tuple[PlcMember, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    def member_named(self, name: str) -> PlcMember | None:
        normalized = name.lower()
        for member in self.members:
            if member.name.lower() == normalized:
                return member
        return None


@dataclass(frozen=True)
class PlcTag:
    name: str
    data_type: str
    scope: str = "Global"
    tag_type: str = "Base"
    array_dimensions: tuple[int, ...] = ()
    alias_for: str = ""
    hidden: bool = False
    description: str = ""
    external_access: str = ""
    constant: bool | None = None
    radix: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_alias(self) -> bool:
        return self.tag_type.lower() == "alias" or bool(self.alias_for)

    @property
    def scoped_name(self) -> str:
        return self.name if self.scope == "Global" else f"{self.scope}.{self.name}"


@dataclass(frozen=True)
class PlcInstructionTagReference:
    original: str
    base_tag: str
    member_path: str = ""
    operand_index: int = 0
    role: str = "unknown"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlcInstruction:
    mnemonic: str
    operands: tuple[str, ...] = ()
    tag_references: tuple[PlcInstructionTagReference, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlcRung:
    number: int
    rung_type: str = ""
    text: str = ""
    comment: str = ""
    instructions: tuple[PlcInstruction, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlcRoutine:
    name: str
    routine_type: str = ""
    rungs: tuple[PlcRung, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlcProgram:
    name: str
    main_routine_name: str = ""
    tags: tuple[PlcTag, ...] = ()
    routines: tuple[PlcRoutine, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlcTask:
    name: str
    task_type: str = ""
    priority: int | None = None
    rate: int | None = None
    watchdog: int | None = None
    disable_update_outputs: bool | None = None
    inhibit_task: bool | None = None
    scheduled_programs: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlcController:
    name: str
    processor_type: str = ""
    major_version: int | None = None
    comm_path: str = ""
    data_types: tuple[PlcDataType, ...] = ()
    tags: tuple[PlcTag, ...] = ()
    programs: tuple[PlcProgram, ...] = ()
    tasks: tuple[PlcTask, ...] = ()
    source_path: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def all_tags(self) -> tuple[PlcTag, ...]:
        program_tags = tuple(tag for program in self.programs for tag in program.tags)
        return self.tags + program_tags

    def global_tag_named(self, name: str) -> PlcTag | None:
        return self.tag_named("Global", name)

    def tag_named(self, scope: str, name: str) -> PlcTag | None:
        normalized = name.lower()
        for tag in self.all_tags():
            if tag.scope == scope and tag.name.lower() == normalized:
                return tag
        return None

    def data_type_named(self, name: str) -> PlcDataType | None:
        normalized = name.lower()
        for data_type in self.data_types:
            if data_type.name.lower() == normalized:
                return data_type
        return None

    def program_named(self, name: str) -> PlcProgram | None:
        normalized = name.lower()
        for program in self.programs:
            if program.name.lower() == normalized:
                return program
        return None

    def task_named(self, name: str) -> PlcTask | None:
        normalized = name.lower()
        for task in self.tasks:
            if task.name.lower() == normalized:
                return task
        return None


@dataclass(frozen=True)
class PlcProject:
    controllers: tuple[PlcController, ...]
    source_path: str = ""
    source_sha256: str = ""

    def controller_named(self, name: str) -> PlcController | None:
        normalized = name.lower()
        for controller in self.controllers:
            if controller.name.lower() == normalized:
                return controller
        return None

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "controller_count": len(self.controllers),
            "controllers": [
                {
                    "name": controller.name,
                    "processor_type": controller.processor_type,
                    "major_version": controller.major_version,
                    "data_type_count": len(controller.data_types),
                    "global_tag_count": len(controller.tags),
                    "program_count": len(controller.programs),
                    "task_count": len(controller.tasks),
                    "routine_count": sum(len(program.routines) for program in controller.programs),
                    "rung_count": sum(len(routine.rungs) for program in controller.programs for routine in program.routines),
                    "program_tag_count": sum(len(program.tags) for program in controller.programs),
                }
                for controller in self.controllers
            ],
        }


def parse_dimensions(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    cleaned = value.strip().strip("[]")
    if not cleaned or cleaned == "0":
        return ()
    dimensions: list[int] = []
    for part in cleaned.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            dimensions.append(int(part))
        except ValueError:
            return ()
    return tuple(dimensions)


def source_label(path: str | Path) -> str:
    return str(Path(path)) if path else ""


def parse_rll_instructions(text: str) -> tuple[PlcInstruction, ...]:
    instructions: list[PlcInstruction] = []
    for match in INSTRUCTION_RE.finditer(text):
        mnemonic = match.group("mnemonic").upper()
        operands = tuple(operand.strip() for operand in match.group("operands").split(","))
        references = tuple(
            reference
            for operand_index, operand in enumerate(operands)
            if (reference := parse_instruction_tag_reference(mnemonic, operand, operand_index)) is not None
        )
        instructions.append(
            PlcInstruction(
                mnemonic=mnemonic,
                operands=operands,
                tag_references=references,
                raw={"source": match.group(0), "start": match.start(), "end": match.end()},
            )
        )
    return tuple(instructions)


def parse_instruction_tag_reference(
    mnemonic: str, operand: str, operand_index: int
) -> PlcInstructionTagReference | None:
    cleaned = operand.strip()
    if not cleaned or cleaned == "?" or cleaned.isdigit() or cleaned.startswith("'") or cleaned.startswith('"'):
        return None
    match = TAG_OPERAND_RE.match(cleaned)
    if match is None:
        return None
    base_tag = match.group("base")
    member_path = (match.group("member") or "").lstrip(".")
    role = reference_role(mnemonic, operand_index)
    if role in {"count", "routine"}:
        return None
    return PlcInstructionTagReference(
        original=cleaned,
        base_tag=base_tag,
        member_path=member_path,
        operand_index=operand_index,
        role=role,
        raw={"mnemonic": mnemonic, "operand": cleaned},
    )


def reference_role(mnemonic: str, operand_index: int) -> str:
    roles = REFERENCE_ROLES.get(mnemonic.upper(), ())
    if operand_index >= len(roles):
        return "unknown"
    return roles[operand_index]
