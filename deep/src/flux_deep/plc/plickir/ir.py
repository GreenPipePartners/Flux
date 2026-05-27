from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


PlickirInstructionKind = Literal[
    "contact.no",
    "contact.nc",
    "timer.ton",
    "coil.latch",
    "coil.unlatch",
    "copy",
    "routine.call",
]

@dataclass(frozen=True)
class PlickirSourceRef:
    source_kind: str
    controller: str = ""
    program: str = ""
    routine: str = ""
    rung_number: int | None = None
    instruction_index: int | None = None
    original: str = ""


@dataclass(frozen=True)
class PlickirDiagnostic:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    source: PlickirSourceRef


@dataclass(frozen=True)
class PlickirTagRef:
    name: str
    scope: str = "Global"
    member_path: str = ""

    @property
    def path(self) -> str:
        base = self.name if self.scope == "Global" else f"{self.scope}.{self.name}"
        return f"{base}.{self.member_path}" if self.member_path else base


@dataclass(frozen=True)
class PlickirTimerInitial:
    preset_ms: int = 0
    accumulated_ms: int = 0


PlickirOperandValue: TypeAlias = str | int | bool | PlickirTagRef
PlickirInitialValue: TypeAlias = str | int | bool | PlickirTimerInitial | None


@dataclass(frozen=True)
class PlickirTag:
    name: str
    data_type: str
    scope: str
    initial_value: PlickirInitialValue = None
    source: PlickirSourceRef = PlickirSourceRef("tag")


@dataclass(frozen=True)
class PlickirInstruction:
    kind: PlickirInstructionKind
    operands: tuple[PlickirOperandValue, ...]
    source: PlickirSourceRef

    @property
    def primary_tag(self) -> PlickirTagRef | None:
        for operand in self.operands:
            if isinstance(operand, PlickirTagRef):
                return operand
        return None


@dataclass(frozen=True)
class PlickirNetwork:
    index: int
    instructions: tuple[PlickirInstruction, ...]
    source_text: str = ""

    @property
    def contacts(self) -> tuple[PlickirInstruction, ...]:
        return tuple(instruction for instruction in self.instructions if instruction.kind.startswith("contact."))

    @property
    def actions(self) -> tuple[PlickirInstruction, ...]:
        return tuple(instruction for instruction in self.instructions if not instruction.kind.startswith("contact."))


@dataclass(frozen=True)
class PlickirRung:
    number: int
    networks: tuple[PlickirNetwork, ...]
    source: PlickirSourceRef


@dataclass(frozen=True)
class PlickirRoutine:
    name: str
    routine_type: str
    rungs: tuple[PlickirRung, ...]
    source: PlickirSourceRef


@dataclass(frozen=True)
class PlickirProgram:
    name: str
    main_routine_name: str
    tags: tuple[PlickirTag, ...]
    routines: tuple[PlickirRoutine, ...]
    source: PlickirSourceRef


@dataclass(frozen=True)
class PlickirTask:
    name: str
    task_type: str
    scheduled_programs: tuple[str, ...]
    source: PlickirSourceRef


@dataclass(frozen=True)
class PlickirController:
    name: str
    tags: tuple[PlickirTag, ...]
    programs: tuple[PlickirProgram, ...]
    tasks: tuple[PlickirTask, ...]
    source: PlickirSourceRef

    def program_named(self, name: str) -> PlickirProgram | None:
        normalized = name.lower()
        for program in self.programs:
            if program.name.lower() == normalized:
                return program
        return None

    def tag_named(self, scope: str, name: str) -> PlickirTag | None:
        normalized = name.lower()
        for tag in self.tags + tuple(tag for program in self.programs for tag in program.tags):
            if tag.scope == scope and tag.name.lower() == normalized:
                return tag
        return None


@dataclass(frozen=True)
class PlickirProject:
    controllers: tuple[PlickirController, ...]
    diagnostics: tuple[PlickirDiagnostic, ...] = ()

    def controller_named(self, name: str) -> PlickirController | None:
        normalized = name.lower()
        for controller in self.controllers:
            if controller.name.lower() == normalized:
                return controller
        return None

    def counts(self) -> dict[str, int]:
        return {
            "controller_count": len(self.controllers),
            "program_count": sum(len(controller.programs) for controller in self.controllers),
            "task_count": sum(len(controller.tasks) for controller in self.controllers),
            "routine_count": sum(len(program.routines) for controller in self.controllers for program in controller.programs),
            "rung_count": sum(
                len(routine.rungs)
                for controller in self.controllers
                for program in controller.programs
                for routine in program.routines
            ),
            "network_count": sum(
                len(rung.networks)
                for controller in self.controllers
                for program in controller.programs
                for routine in program.routines
                for rung in routine.rungs
            ),
            "instruction_count": sum(
                len(network.instructions)
                for controller in self.controllers
                for program in controller.programs
                for routine in program.routines
                for rung in routine.rungs
                for network in rung.networks
            ),
            "diagnostic_count": len(self.diagnostics),
        }
