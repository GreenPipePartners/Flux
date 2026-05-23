from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
class PlcProgram:
    name: str
    tags: tuple[PlcTag, ...] = ()
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
