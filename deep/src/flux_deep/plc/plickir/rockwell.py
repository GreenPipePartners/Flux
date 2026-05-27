from __future__ import annotations

from typing import Any

from flux_deep.plc.plickir.ir import (
    PlickirController,
    PlickirDiagnostic,
    PlickirInstruction,
    PlickirInstructionKind,
    PlickirNetwork,
    PlickirProgram,
    PlickirProject,
    PlickirRoutine,
    PlickirRung,
    PlickirSourceRef,
    PlickirTag,
    PlickirTagRef,
    PlickirTask,
    PlickirTimerInitial,
)
from flux_deep.plc.plickir.normalize import split_parallel_networks


INSTRUCTION_KIND_BY_MNEMONIC: dict[str, PlickirInstructionKind] = {
    "XIC": "contact.no",
    "XIO": "contact.nc",
    "TON": "timer.ton",
    "OTL": "coil.latch",
    "OTU": "coil.unlatch",
    "COP": "copy",
    "JSR": "routine.call",
}


def lift_rockwell_project(project: Any) -> PlickirProject:
    diagnostics: list[PlickirDiagnostic] = []
    controllers = tuple(lift_controller(controller, diagnostics) for controller in project.controllers)
    return PlickirProject(controllers=controllers, diagnostics=tuple(diagnostics))


def lift_controller(controller: Any, diagnostics: list[PlickirDiagnostic]) -> PlickirController:
    source = PlickirSourceRef("controller", controller=controller.name)
    return PlickirController(
        name=controller.name,
        tags=tuple(lift_tag(tag, controller=controller.name) for tag in controller.tags),
        programs=tuple(lift_program(controller, program, diagnostics) for program in controller.programs),
        tasks=tuple(lift_task(controller, task) for task in controller.tasks),
        source=source,
    )


def lift_program(controller: Any, program: Any, diagnostics: list[PlickirDiagnostic]) -> PlickirProgram:
    source = PlickirSourceRef("program", controller=controller.name, program=program.name)
    return PlickirProgram(
        name=program.name,
        main_routine_name=program.main_routine_name,
        tags=tuple(lift_tag(tag, controller=controller.name) for tag in program.tags),
        routines=tuple(lift_routine(controller, program, routine, diagnostics) for routine in program.routines),
        source=source,
    )


def lift_task(controller: Any, task: Any) -> PlickirTask:
    return PlickirTask(
        name=task.name,
        task_type=task.task_type,
        scheduled_programs=tuple(task.scheduled_programs),
        source=PlickirSourceRef("task", controller=controller.name, original=task.name),
    )


def lift_routine(controller: Any, program: Any, routine: Any, diagnostics: list[PlickirDiagnostic]) -> PlickirRoutine:
    source = PlickirSourceRef("routine", controller=controller.name, program=program.name, routine=routine.name)
    return PlickirRoutine(
        name=routine.name,
        routine_type=routine.routine_type,
        rungs=tuple(lift_rung(controller, program, routine, rung, diagnostics) for rung in routine.rungs),
        source=source,
    )


def lift_rung(controller: Any, program: Any, routine: Any, rung: Any, diagnostics: list[PlickirDiagnostic]) -> PlickirRung:
    source = PlickirSourceRef(
        "rung",
        controller=controller.name,
        program=program.name,
        routine=routine.name,
        rung_number=rung.number,
        original=rung.text,
    )
    networks = split_parallel_networks(rung.text)
    return PlickirRung(
        number=rung.number,
        networks=tuple(
            lift_network(controller, program, routine, rung, network_index, network_text, diagnostics)
            for network_index, network_text in enumerate(networks)
        ),
        source=source,
    )


def lift_network(
    controller: Any,
    program: Any,
    routine: Any,
    rung: Any,
    network_index: int,
    network_text: str,
    diagnostics: list[PlickirDiagnostic],
) -> PlickirNetwork:
    instructions: list[PlickirInstruction] = []
    is_parallel = len(split_parallel_networks(rung.text)) > 1
    for instruction_index, instruction in enumerate(rung.instructions):
        source_text = str(instruction.raw.get("source", ""))
        if is_parallel and source_text and source_text not in network_text:
            continue
        lifted = lift_instruction(controller, program, routine, rung, instruction_index, instruction, diagnostics)
        if lifted is not None:
            instructions.append(lifted)
    return PlickirNetwork(index=network_index, instructions=tuple(instructions), source_text=network_text)


def lift_instruction(
    controller: Any,
    program: Any,
    routine: Any,
    rung: Any,
    instruction_index: int,
    instruction: Any,
    diagnostics: list[PlickirDiagnostic],
) -> PlickirInstruction | None:
    mnemonic = instruction.mnemonic.upper()
    source = PlickirSourceRef(
        "instruction",
        controller=controller.name,
        program=program.name,
        routine=routine.name,
        rung_number=rung.number,
        instruction_index=instruction_index,
        original=str(instruction.raw.get("source", "")),
    )
    kind = INSTRUCTION_KIND_BY_MNEMONIC.get(mnemonic)
    if kind is None:
        diagnostics.append(PlickirDiagnostic("error", "unsupported_instruction", f"Unsupported RLL instruction {mnemonic}", source))
        return None

    if mnemonic == "JSR":
        operands = tuple(operand.strip() for operand in instruction.operands[:1] if operand.strip())
    else:
        operands = tuple(lift_operand(program.name, operand) for operand in instruction.operands if operand != "?")
    return PlickirInstruction(kind=kind, operands=operands, source=source)


def lift_operand(scope: str, operand: str) -> str | int | PlickirTagRef:
    cleaned = operand.strip()
    if cleaned.isdigit():
        return int(cleaned)
    if "." in cleaned:
        name, member_path = cleaned.split(".", 1)
        return PlickirTagRef(name=name, scope=scope, member_path=member_path)
    return PlickirTagRef(name=cleaned, scope=scope)


def lift_tag(tag: Any, *, controller: str) -> PlickirTag:
    return PlickirTag(
        name=tag.name,
        data_type=tag.data_type,
        scope=tag.scope,
        initial_value=initial_value(tag.data_type, tag.raw),
        source=PlickirSourceRef("tag", controller=controller, program=tag.scope if tag.scope != "Global" else "", original=tag.name),
    )


def initial_value(data_type: str, raw: dict[str, Any]) -> str | int | bool | PlickirTimerInitial | None:
    normalized = data_type.upper()
    if normalized == "STRING":
        return string_initial(raw)
    l5k = l5k_payload(raw)
    if normalized == "BOOL":
        return l5k in {"1", "true", "True"}
    if normalized in {"DINT", "INT", "SINT"}:
        return int(l5k or "0")
    if normalized == "TIMER":
        parts = l5k_array(l5k)
        return PlickirTimerInitial(
            preset_ms=int(parts[1]) if len(parts) > 1 else 0,
            accumulated_ms=int(parts[2]) if len(parts) > 2 else 0,
        )
    return None


def string_initial(raw: dict[str, Any]) -> str:
    for payload in raw.get("data", []):
        if str(payload.get("format", "")).lower() == "string":
            return unquoted(str(payload.get("text", "")).strip())
    parts = l5k_array(l5k_payload(raw))
    if len(parts) < 2:
        return ""
    return parts[1].replace("$00", "")[: int(parts[0])]


def l5k_payload(raw: dict[str, Any]) -> str:
    for payload in raw.get("data", []):
        if str(payload.get("format", "")).lower() == "l5k":
            return str(payload.get("text", "")).strip()
    return ""


def l5k_array(value: str) -> tuple[str, ...]:
    stripped = value.strip().strip("[]")
    return tuple(part.strip().strip("'") for part in stripped.split(",") if part.strip())


def unquoted(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value
