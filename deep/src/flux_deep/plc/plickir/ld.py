from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from flux_deep.plc.plickir.ir import (
    PlickirController,
    PlickirInstruction,
    PlickirNetwork,
    PlickirProgram,
    PlickirProject,
    PlickirRoutine,
    PlickirTag,
    PlickirTagRef,
    PlickirTimerInitial,
)


PLCOPEN_NS = "http://www.plcopen.org/xml/tc6_0201"
XML_DECLARATION = "<?xml version='1.0' encoding='utf-8'?>\n"
GENERATED_TIMESTAMP = "2026-05-26T00:00:00"

ET.register_namespace("", PLCOPEN_NS)


class PlickirLdError(ValueError):
    """Raised when plickir IR cannot be represented by the first LD target."""


def render_plcopen_ld_project(
    project: PlickirProject,
    *,
    controller_name: str | None = None,
) -> str:
    """Render a minimal OpenPLC Editor/Beremiz PLCopen LD project XML document."""

    controller = _select_controller(project, controller_name)
    root = _element("project")
    _add_file_header(root)
    _add_content_header(root, controller.name)
    _add_types(root, controller)
    _add_instances(root, controller)
    ET.indent(root, space="  ")
    return XML_DECLARATION + ET.tostring(root, encoding="unicode") + "\n"


def write_plcopen_ld_project(
    project: PlickirProject,
    output_dir: str | Path,
    *,
    controller_name: str | None = None,
) -> Path:
    """Write an OpenPLC Editor project folder containing `plc.xml`."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    plc_xml = destination / "plc.xml"
    plc_xml.write_text(
        render_plcopen_ld_project(project, controller_name=controller_name),
        encoding="utf-8",
    )
    return plc_xml


def _select_controller(project: PlickirProject, controller_name: str | None) -> PlickirController:
    if controller_name is not None:
        controller = project.controller_named(controller_name)
        if controller is None:
            raise PlickirLdError(f"Controller {controller_name!r} not found")
        return controller
    if len(project.controllers) != 1:
        raise PlickirLdError("controller_name is required when project has multiple controllers")
    return project.controllers[0]


def _add_file_header(root: ET.Element) -> None:
    ET.SubElement(
        root,
        _tag("fileHeader"),
        {
            "companyName": "Flux",
            "productName": "deep.plickir",
            "productVersion": "0.1",
            "creationDateTime": GENERATED_TIMESTAMP,
        },
    )


def _add_content_header(root: ET.Element, controller_name: str) -> None:
    content = ET.SubElement(
        root,
        _tag("contentHeader"),
        {"name": controller_name, "modificationDateTime": GENERATED_TIMESTAMP},
    )
    coordinate_info = ET.SubElement(content, _tag("coordinateInfo"))
    for language in ("fbd", "ld", "sfc"):
        node = ET.SubElement(coordinate_info, _tag(language))
        ET.SubElement(node, _tag("scaling"), {"x": "10", "y": "10"})


def _add_types(root: ET.Element, controller: PlickirController) -> None:
    types = ET.SubElement(root, _tag("types"))
    ET.SubElement(types, _tag("dataTypes"))
    pous = ET.SubElement(types, _tag("pous"))
    for program in controller.programs:
        _add_program_pou(pous, program)


def _add_program_pou(parent: ET.Element, program: PlickirProgram) -> None:
    pou = ET.SubElement(parent, _tag("pou"), {"name": program.name, "pouType": "program"})
    interface = ET.SubElement(pou, _tag("interface"))
    local_vars = ET.SubElement(interface, _tag("localVars"))
    for tag in program.tags:
        _add_variable(local_vars, tag)

    body = ET.SubElement(pou, _tag("body"))
    ld = ET.SubElement(body, _tag("LD"))
    _LdBodyWriter(ld, program, _select_main_routine(program)).write()


def _add_variable(parent: ET.Element, tag: PlickirTag) -> None:
    variable = ET.SubElement(parent, _tag("variable"), {"name": tag.name})
    type_node = ET.SubElement(variable, _tag("type"))
    data_type = tag.data_type.upper()
    if data_type == "TIMER":
        ET.SubElement(type_node, _tag("derived"), {"name": "TON"})
    else:
        ET.SubElement(type_node, _tag(_plcopen_type_name(data_type)))

    initial_value = _initial_value_token(tag)
    if initial_value is not None:
        initial = ET.SubElement(variable, _tag("initialValue"))
        ET.SubElement(initial, _tag("simpleValue"), {"value": initial_value})


def _initial_value_token(tag: PlickirTag) -> str | None:
    if isinstance(tag.initial_value, PlickirTimerInitial) or tag.initial_value is None:
        return None
    if isinstance(tag.initial_value, bool):
        return "TRUE" if tag.initial_value else "FALSE"
    if isinstance(tag.initial_value, int):
        return str(tag.initial_value)
    if isinstance(tag.initial_value, str):
        return "'" + tag.initial_value.replace("'", "''") + "'"
    return None


def _plcopen_type_name(data_type: str) -> str:
    if data_type == "STRING":
        return "string"
    if data_type == "WSTRING":
        return "wstring"
    return data_type


def _select_main_routine(program: PlickirProgram) -> PlickirRoutine:
    if program.main_routine_name:
        for routine in program.routines:
            if routine.name == program.main_routine_name:
                return routine
    if not program.routines:
        raise PlickirLdError(f"Program {program.name!r} has no routines")
    return program.routines[0]


def _add_instances(root: ET.Element, controller: PlickirController) -> None:
    instances = ET.SubElement(root, _tag("instances"))
    configurations = ET.SubElement(instances, _tag("configurations"))
    configuration = ET.SubElement(configurations, _tag("configuration"), {"name": "Config0"})
    resource = ET.SubElement(configuration, _tag("resource"), {"name": "Res0"})
    if controller.tasks:
        for task_index, task in enumerate(controller.tasks):
            task_node = ET.SubElement(
                resource,
                _tag("task"),
                {"name": task.name, "priority": str(task_index), "interval": "T#100ms"},
            )
            for program_name in task.scheduled_programs:
                ET.SubElement(
                    task_node,
                    _tag("pouInstance"),
                    {"name": f"{program_name}Instance", "typeName": program_name},
                )
    else:
        for program in controller.programs:
            ET.SubElement(
                resource,
                _tag("pouInstance"),
                {"name": f"{program.name}Instance", "typeName": program.name},
            )


class _LdBodyWriter:
    def __init__(self, parent: ET.Element, program: PlickirProgram, routine: PlickirRoutine) -> None:
        self.parent = parent
        self.program = program
        self.routine = routine
        self.next_local_id = 1
        self.left_rail_id = self._next_id()
        self.right_rail_id = self._next_id()
        self.output_positions: dict[int, tuple[int, int]] = {}
        self.right_connections: list[tuple[int, int, tuple[int, int], str | None]] = []

    def write(self) -> None:
        networks = self._expanded_networks(self.routine)
        if not networks:
            raise PlickirLdError(f"Routine {self.routine.name!r} has no networks")
        self._add_left_power_rail(len(networks))
        right_rail = self._add_right_power_rail()
        for row_index, network in enumerate(networks):
            self._add_network(row_index, network)
        self._add_right_power_connections(right_rail, len(networks))

    def _expanded_networks(self, routine: PlickirRoutine, call_stack: tuple[str, ...] = ()) -> tuple[PlickirNetwork, ...]:
        if routine.name in call_stack:
            raise PlickirLdError(f"Recursive routine call detected: {' -> '.join((*call_stack, routine.name))}")
        networks: list[PlickirNetwork] = []
        for rung in routine.rungs:
            for network in rung.networks:
                call = _unconditional_routine_call(network)
                if call is None:
                    networks.append(network)
                    continue
                called_routine = _routine_named(self.program, call)
                if called_routine is None:
                    raise PlickirLdError(f"Routine call target {call!r} not found in program {self.program.name!r}")
                networks.extend(self._expanded_networks(called_routine, (*call_stack, routine.name)))
        return tuple(networks)

    def _add_left_power_rail(self, network_count: int) -> None:
        rail = ET.SubElement(
            self.parent,
            _tag("leftPowerRail"),
            {"localId": str(self.left_rail_id), "height": str(max(80, network_count * 80)), "width": "10"},
        )
        _add_position(rail, 90, 110)
        for row_index in range(network_count):
            output = ET.SubElement(rail, _tag("connectionPointOut"), {"formalParameter": ""})
            _add_rel_position(output, 10, self._row_rel_y(row_index))

    def _add_right_power_rail(self) -> ET.Element:
        rail = ET.SubElement(
            self.parent,
            _tag("rightPowerRail"),
            {"localId": str(self.right_rail_id), "height": "80", "width": "10"},
        )
        _add_position(rail, 990, 110)
        return rail

    def _add_right_power_connections(self, rail: ET.Element, network_count: int) -> None:
        rail.set("height", str(max(80, network_count * 80)))
        by_row = {
            row: (source_id, source_position, formal_parameter)
            for row, source_id, source_position, formal_parameter in self.right_connections
        }
        for row_index in range(network_count):
            input_node = ET.SubElement(rail, _tag("connectionPointIn"))
            _add_rel_position(input_node, 0, self._row_rel_y(row_index))
            source = by_row.get(row_index)
            if source is not None:
                source_id, source_position, formal_parameter = source
                target_position = (990, self._row_y(row_index) + 10)
                _add_connection(
                    input_node,
                    source_id,
                    source_position=source_position,
                    target_position=target_position,
                    formal_parameter=formal_parameter,
                )

    def _add_network(self, row_index: int, network: PlickirNetwork) -> None:
        row_y = self._row_y(row_index)
        left_position = (100, row_y + 10)
        current_id = self.left_rail_id
        current_position = left_position
        current_formal_parameter: str | None = None
        current_x = 100
        for instruction in network.instructions:
            if instruction.kind in {"contact.no", "contact.nc"}:
                current_x += 80
                current_id, current_position, current_formal_parameter = self._add_contact(
                    instruction,
                    current_id,
                    current_position,
                    current_x,
                    row_y,
                )
            elif instruction.kind == "timer.ton":
                current_x += 150
                current_id, current_position, current_formal_parameter = self._add_ton_block(
                    instruction,
                    current_id,
                    current_position,
                    left_position,
                    current_x,
                    row_y,
                )
            elif instruction.kind in {"coil.latch", "coil.unlatch"}:
                current_x += 150
                current_id, current_position, current_formal_parameter = self._add_coil(
                    instruction,
                    current_id,
                    current_position,
                    current_x,
                    row_y,
                )
            elif instruction.kind == "copy":
                current_x += 150
                current_id, current_position, current_formal_parameter = self._add_move_block(
                    instruction,
                    current_id,
                    current_position,
                    current_x,
                    row_y,
                )
            else:
                raise PlickirLdError(f"Unsupported LD instruction kind {instruction.kind!r}")
        self.right_connections.append((row_index, current_id, current_position, current_formal_parameter))

    def _add_contact(
        self,
        instruction: PlickirInstruction,
        source_id: int,
        source_position: tuple[int, int],
        x: int,
        y: int,
    ) -> tuple[int, tuple[int, int], None]:
        tag = _single_tag_operand(instruction)
        local_id = self._next_id()
        contact = ET.SubElement(
            self.parent,
            _tag("contact"),
            {
                "localId": str(local_id),
                "height": "20",
                "width": "30",
                "negated": _xml_bool(instruction.kind == "contact.nc"),
            },
        )
        _add_position(contact, x, y)
        input_node = ET.SubElement(contact, _tag("connectionPointIn"))
        _add_rel_position(input_node, 0, 10)
        _add_connection(input_node, source_id, source_position=source_position, target_position=(x, y + 10))
        output_node = ET.SubElement(contact, _tag("connectionPointOut"))
        _add_rel_position(output_node, 30, 10)
        output_position = (x + 30, y + 10)
        self.output_positions[local_id] = output_position
        variable = ET.SubElement(contact, _tag("variable"))
        variable.text = _tag_expression(tag, self.program)
        return local_id, output_position, None

    def _add_coil(
        self,
        instruction: PlickirInstruction,
        source_id: int,
        source_position: tuple[int, int],
        x: int,
        y: int,
    ) -> tuple[int, tuple[int, int], None]:
        tag = _single_tag_operand(instruction)
        local_id = self._next_id()
        storage = "set" if instruction.kind == "coil.latch" else "reset"
        coil = ET.SubElement(
            self.parent,
            _tag("coil"),
            {
                "localId": str(local_id),
                "height": "20",
                "width": "30",
                "negated": "false",
                "storage": storage,
            },
        )
        _add_position(coil, x, y)
        input_node = ET.SubElement(coil, _tag("connectionPointIn"))
        _add_rel_position(input_node, 0, 10)
        _add_connection(input_node, source_id, source_position=source_position, target_position=(x, y + 10))
        output_node = ET.SubElement(coil, _tag("connectionPointOut"))
        _add_rel_position(output_node, 30, 10)
        output_position = (x + 30, y + 10)
        self.output_positions[local_id] = output_position
        variable = ET.SubElement(coil, _tag("variable"))
        variable.text = _tag_expression(tag, self.program)
        return local_id, output_position, None

    def _add_ton_block(
        self,
        instruction: PlickirInstruction,
        source_id: int,
        source_position: tuple[int, int],
        left_position: tuple[int, int],
        x: int,
        y: int,
    ) -> tuple[int, tuple[int, int], str]:
        timer = _single_tag_operand(instruction)
        timer_tag = _find_program_tag(self.program, timer.name)
        preset_ms = 0
        if isinstance(timer_tag.initial_value, PlickirTimerInitial):
            preset_ms = timer_tag.initial_value.preset_ms
        preset_id = self._add_in_variable(f"T#{preset_ms}ms", x - 110, y + 70)
        preset_position = self.output_positions[preset_id]
        local_id = self._next_id()
        block_y = y - 40
        block = ET.SubElement(
            self.parent,
            _tag("block"),
            {
                "localId": str(local_id),
                "typeName": "TON",
                "instanceName": _tag_expression(timer, self.program),
                "height": "140",
                "width": "90",
            },
        )
        _add_position(block, x, block_y)
        inputs = ET.SubElement(block, _tag("inputVariables"))
        self._add_block_input(inputs, "EN", self.left_rail_id, left_position, x, block_y, 0, 40)
        self._add_block_input(inputs, "IN", source_id, source_position, x, block_y, 0, 80)
        self._add_block_input(inputs, "PT", preset_id, preset_position, x, block_y, 0, 120)
        ET.SubElement(block, _tag("inOutVariables"))
        outputs = ET.SubElement(block, _tag("outputVariables"))
        self._add_block_output(outputs, "ENO", 90, 40)
        self._add_block_output(outputs, "Q", 90, 80)
        self._add_block_output(outputs, "ET", 90, 120)
        output_position = (x + 90, block_y + 40)
        self.output_positions[local_id] = output_position
        return local_id, output_position, "ENO"

    def _add_move_block(
        self,
        instruction: PlickirInstruction,
        source_id: int,
        source_position: tuple[int, int],
        x: int,
        y: int,
    ) -> tuple[int, tuple[int, int], None]:
        if len(instruction.operands) != 3:
            raise PlickirLdError("copy instruction requires source, destination, and count operands")
        source, destination, count = instruction.operands
        if not isinstance(source, PlickirTagRef) or not isinstance(destination, PlickirTagRef):
            raise PlickirLdError("copy source and destination operands must be tag references")
        if count != 1:
            raise PlickirLdError("first LD copy lowering only supports count 1")
        value_id = self._add_in_variable(_tag_expression(source, self.program), x - 110, y + 40)
        value_position = self.output_positions[value_id]
        block_id = self._next_id()
        block_y = y - 10
        block = ET.SubElement(
            self.parent,
            _tag("block"),
            {"localId": str(block_id), "typeName": "MOVE", "height": "80", "width": "90"},
        )
        _add_position(block, x, block_y)
        inputs = ET.SubElement(block, _tag("inputVariables"))
        self._add_block_input(inputs, "EN", source_id, source_position, x, block_y, 0, 30)
        self._add_block_input(inputs, "IN", value_id, value_position, x, block_y, 0, 60)
        ET.SubElement(block, _tag("inOutVariables"))
        outputs = ET.SubElement(block, _tag("outputVariables"))
        self._add_block_output(outputs, "ENO", 90, 30)
        self._add_block_output(outputs, "OUT", 90, 60)
        block_output_position = (x + 90, block_y + 60)
        self.output_positions[block_id] = block_output_position
        out_id = self._next_id()
        out_variable = ET.SubElement(
            self.parent,
            _tag("outVariable"),
            {"localId": str(out_id), "height": "40", "width": "100"},
        )
        _add_position(out_variable, x + 150, y - 10)
        input_node = ET.SubElement(out_variable, _tag("connectionPointIn"))
        _add_rel_position(input_node, 0, 20)
        _add_connection(
            input_node,
            block_id,
            source_position=block_output_position,
            target_position=(x + 150, y + 10),
            formal_parameter="OUT",
        )
        expression = ET.SubElement(out_variable, _tag("expression"))
        expression.text = _tag_expression(destination, self.program)
        output_position = (x + 250, y + 10)
        self.output_positions[out_id] = output_position
        return out_id, output_position, None

    def _add_in_variable(self, expression: str, x: int, y: int) -> int:
        local_id = self._next_id()
        in_variable = ET.SubElement(
            self.parent,
            _tag("inVariable"),
            {"localId": str(local_id), "height": "40", "width": "80", "negated": "false"},
        )
        _add_position(in_variable, x, y)
        output_node = ET.SubElement(in_variable, _tag("connectionPointOut"))
        _add_rel_position(output_node, 80, 20)
        self.output_positions[local_id] = (x + 80, y + 20)
        expression_node = ET.SubElement(in_variable, _tag("expression"))
        expression_node.text = expression
        return local_id

    def _add_block_input(
        self,
        parent: ET.Element,
        formal_parameter: str,
        source_id: int,
        source_position: tuple[int, int],
        block_x: int,
        block_y: int,
        rel_x: int,
        rel_y: int,
    ) -> None:
        variable = ET.SubElement(parent, _tag("variable"), {"formalParameter": formal_parameter})
        input_node = ET.SubElement(variable, _tag("connectionPointIn"))
        _add_rel_position(input_node, rel_x, rel_y)
        _add_connection(
            input_node,
            source_id,
            source_position=source_position,
            target_position=(block_x + rel_x, block_y + rel_y),
        )

    def _add_block_output(
        self,
        parent: ET.Element,
        formal_parameter: str,
        rel_x: int,
        rel_y: int,
    ) -> None:
        variable = ET.SubElement(parent, _tag("variable"), {"formalParameter": formal_parameter})
        output_node = ET.SubElement(variable, _tag("connectionPointOut"))
        _add_rel_position(output_node, rel_x, rel_y)

    def _next_id(self) -> int:
        local_id = self.next_local_id
        self.next_local_id += 1
        return local_id

    @staticmethod
    def _row_y(row_index: int) -> int:
        return 120 + row_index * 80

    @staticmethod
    def _row_rel_y(row_index: int) -> int:
        return 20 + row_index * 80


def _single_tag_operand(instruction: PlickirInstruction) -> PlickirTagRef:
    if len(instruction.operands) != 1 or not isinstance(instruction.operands[0], PlickirTagRef):
        raise PlickirLdError(f"{instruction.kind} requires exactly one tag operand")
    return instruction.operands[0]


def _find_program_tag(program: PlickirProgram, name: str) -> PlickirTag:
    normalized = name.lower()
    for tag in program.tags:
        if tag.name.lower() == normalized:
            return tag
    raise PlickirLdError(f"Program {program.name!r} does not define tag {name!r}")


def _routine_named(program: PlickirProgram, name: str) -> PlickirRoutine | None:
    normalized = name.lower()
    for routine in program.routines:
        if routine.name.lower() == normalized:
            return routine
    return None


def _unconditional_routine_call(network: PlickirNetwork) -> str | None:
    if len(network.instructions) != 1:
        return None
    instruction = network.instructions[0]
    if instruction.kind != "routine.call" or len(instruction.operands) != 1:
        return None
    operand = instruction.operands[0]
    return operand if isinstance(operand, str) else None


def _tag_expression(ref: PlickirTagRef, program: PlickirProgram) -> str:
    name = ref.name if ref.scope in {"Global", program.name} else ref.path
    if not ref.member_path:
        return name
    member = {"DN": "Q", "ACC": "ET"}.get(ref.member_path.upper(), ref.member_path)
    return f"{name}.{member}"


def _add_position(parent: ET.Element, x: int, y: int) -> None:
    ET.SubElement(parent, _tag("position"), {"x": str(x), "y": str(y)})


def _add_rel_position(parent: ET.Element, x: int, y: int) -> None:
    ET.SubElement(parent, _tag("relPosition"), {"x": str(x), "y": str(y)})


def _add_connection(
    parent: ET.Element,
    source_id: int | str,
    *,
    source_position: tuple[int, int] | None = None,
    target_position: tuple[int, int] | None = None,
    formal_parameter: str | None = None,
) -> None:
    attrs = {"refLocalId": str(source_id)}
    if formal_parameter is not None:
        attrs["formalParameter"] = formal_parameter
    connection = ET.SubElement(parent, _tag("connection"), attrs)
    if target_position is not None and source_position is not None:
        _add_position(connection, *target_position)
        _add_position(connection, *source_position)


def _xml_bool(value: bool) -> str:
    return "true" if value else "false"


def _element(name: str) -> ET.Element:
    return ET.Element(_tag(name))


def _tag(name: str) -> str:
    return f"{{{PLCOPEN_NS}}}{name}"


__all__ = [
    "PLCOPEN_NS",
    "PlickirLdError",
    "render_plcopen_ld_project",
    "write_plcopen_ld_project",
]
