from __future__ import annotations

from django.db import transaction

from .catalog import ensure_catalog
from .models import Circuit
from .models import CircuitParticipant
from .models import CircuitPotential
from .models import Component
from .models import ComponentTemplate
from .models import Connection
from .models import Drive
from .models import DriveIOPoint
from .models import FieldInstrument
from .models import IOPoint
from .models import InternalRelation
from .models import Net
from .models import NetTerminal
from .models import PotentialLabel
from .models import PotentialSystem
from .models import Role
from .models import RoleContinuity
from .models import RoleTerminal
from .models import SchematicSystem
from .models import Source
from .models import SourceConnection
from .models import SourcePotential
from .models import SourceTerminal
from .models import Terminal


@transaction.atomic
def build_basic_motor_starter_system() -> SchematicSystem:
    ensure_catalog()
    delete_existing_system("basic-480-motor-starter")
    system = SchematicSystem.objects.create(
        name="Basic 480 Motor Starter",
        slug="basic-480-motor-starter",
        description="480 VAC motor power circuit with 24 VDC starter control circuit.",
    )

    disconnect = instantiate_component(system, "disconnect_3pole", "DS1", "Main disconnect")
    power_supply = instantiate_component(system, "power_supply_480_to_24vdc", "PS1", "24 VDC power supply")
    starter = instantiate_component(system, "starter_3pole_24vdc", "M1", "Motor starter")
    motor = instantiate_component(system, "motor_3phase", "MOT1", "3-phase motor")
    button = instantiate_component(system, "button_no_24vdc", "PB1", "Start button")

    power_system = PotentialSystem.objects.get(key="480VAC_3PH")
    control_system = PotentialSystem.objects.get(key="24VDC_CONTROL")

    plant_source = create_source(system, "Plant 480 VAC 3PH", "plant_feed", power_system)
    power_source_role = role(power_supply, "24_vdc_source_output")
    control_source = create_source(
        system,
        "PS1 24 VDC Output",
        "component_output",
        control_system,
        producer_component=power_supply,
        producer_role=power_source_role,
    )

    power_circuit = create_circuit(system, "480 VAC motor power", "power", plant_source, power_system, 10)
    control_circuit = create_circuit(system, "24 VDC starter control", "control", control_source, control_system, 20)

    participate(power_circuit, disconnect, "isolation_switch_3p", 10)
    participate(power_circuit, starter, "main_power_contacts", 20)
    participate(power_circuit, motor, "three_phase_load", 30)
    participate(power_circuit, power_supply, "480_vac_input_load", 40)

    participate(control_circuit, power_supply, "24_vdc_source_output", 10)
    participate(control_circuit, button, "normally_open_contact", 20)
    participate(control_circuit, starter, "coil", 30)

    create_motor_power_connections(power_circuit, disconnect, starter, motor, power_supply)
    create_control_connections(control_circuit, power_supply, button, starter)
    create_primitive_boundary_examples(system)

    return system


def delete_existing_system(slug: str) -> None:
    for system in SchematicSystem.objects.filter(slug=slug):
        system.compile_runs.all().delete()
        DriveIOPoint.objects.filter(drive__system=system).delete()
        IOPoint.objects.filter(system=system).delete()
        Drive.objects.filter(system=system).delete()
        FieldInstrument.objects.filter(system=system).delete()
        SourceConnection.objects.filter(circuit__system=system).delete()
        NetTerminal.objects.filter(circuit__system=system).delete()
        Connection.objects.filter(circuit__system=system).delete()
        Net.objects.filter(circuit__system=system).delete()
        CircuitParticipant.objects.filter(circuit__system=system).delete()
        CircuitPotential.objects.filter(circuit__system=system).delete()
        Circuit.objects.filter(system=system).delete()
        SourceTerminal.objects.filter(source__system=system).delete()
        SourcePotential.objects.filter(source__system=system).delete()
        Source.objects.filter(system=system).delete()
        InternalRelation.objects.filter(component__system=system).delete()
        RoleContinuity.objects.filter(role__component__system=system).delete()
        RoleTerminal.objects.filter(role__component__system=system).delete()
        Role.objects.filter(component__system=system).delete()
        Terminal.objects.filter(component__system=system).delete()
        Component.objects.filter(system=system).delete()
        system.delete()


def instantiate_component(system: SchematicSystem, template_key: str, reference: str, name: str = "") -> Component:
    template = ComponentTemplate.objects.get(key=template_key)
    component = Component.objects.create(system=system, template=template, reference=reference, name=name)

    terminals: dict[str, Terminal] = {}
    for terminal_template in template.terminal_templates.all():
        terminals[terminal_template.key] = Terminal.objects.create(
            component=component,
            template=terminal_template,
            key=terminal_template.key,
            label=terminal_template.label,
        )

    roles: dict[str, Role] = {}
    for role_template in template.role_templates.all():
        role_row = Role.objects.create(
            component=component,
            template=role_template,
            key=role_template.key,
            label=role_template.label,
            metadata=role_template.metadata,
        )
        roles[role_template.key] = role_row
        for link in role_template.terminal_links.select_related("terminal_template"):
            RoleTerminal.objects.create(
                role=role_row,
                terminal=terminals[link.terminal_template.key],
                interface_key=link.interface_key,
                usage=link.usage,
                sort_order=link.sort_order,
            )
        for continuity_template in role_template.continuity_templates.select_related(
            "from_terminal_template",
            "to_terminal_template",
        ):
            RoleContinuity.objects.create(
                role=role_row,
                template=continuity_template,
                from_terminal=terminals[continuity_template.from_terminal_template.key],
                to_terminal=terminals[continuity_template.to_terminal_template.key],
                condition_key=continuity_template.condition_key,
                continuity_kind=continuity_template.continuity_kind,
                sort_order=continuity_template.sort_order,
            )

    for relation_template in template.relation_templates.select_related("source_role_template", "target_role_template"):
        InternalRelation.objects.create(
            component=component,
            template=relation_template,
            key=relation_template.key,
            relation_type=relation_template.relation_type,
            source_role=roles[relation_template.source_role_template.key],
            target_role=roles[relation_template.target_role_template.key],
            condition_key=relation_template.condition_key,
            effect_key=relation_template.effect_key,
            metadata=relation_template.metadata,
        )

    return component


def create_source(
    system: SchematicSystem,
    name: str,
    source_kind: str,
    potential_system: PotentialSystem,
    producer_component: Component | None = None,
    producer_role: Role | None = None,
) -> Source:
    source = Source.objects.create(
        system=system,
        name=name,
        source_kind=source_kind,
        potential_system=potential_system,
        producer_component=producer_component,
        producer_role=producer_role,
        nominal_voltage=potential_system.nominal_voltage,
        phase_count=potential_system.phase_count,
        polarity_kind=potential_system.polarity_kind,
    )
    for label in potential_system.labels.all():
        source_potential = SourcePotential.objects.create(
            source=source,
            potential_label=label,
            key=label.key,
            label=label.label,
            sort_order=label.sort_order,
        )
        SourceTerminal.objects.create(
            source=source,
            source_potential=source_potential,
            key=label.key,
            label=label.label,
            sort_order=label.sort_order,
        )
    return source


def create_circuit(
    system: SchematicSystem,
    name: str,
    circuit_kind: str,
    source: Source,
    potential_system: PotentialSystem,
    sort_order: int,
) -> Circuit:
    circuit = Circuit.objects.create(
        system=system,
        name=name,
        circuit_kind=circuit_kind,
        source=source,
        potential_system=potential_system,
        sort_order=sort_order,
    )
    for label in potential_system.labels.all():
        CircuitPotential.objects.create(
            circuit=circuit,
            potential_label=label,
            key=label.key,
            label=label.label,
            sort_order=label.sort_order,
        )
    return circuit


def participate(circuit: Circuit, component: Component, role_key: str, sort_order: int) -> CircuitParticipant:
    return CircuitParticipant.objects.create(
        circuit=circuit,
        component=component,
        role=role(component, role_key),
        sort_order=sort_order,
    )


def create_motor_power_connections(
    circuit: Circuit,
    disconnect: Component,
    starter: Component,
    motor: Component,
    power_supply: Component,
) -> None:
    l1_source = create_net(circuit, "L1_source", "L1", "L1 source side")
    l2_source = create_net(circuit, "L2_source", "L2", "L2 source side")
    l3_source = create_net(circuit, "L3_source", "L3", "L3 source side")
    l1_after_disconnect = create_net(circuit, "L1_after_disconnect", "L1", "L1 after disconnect")
    l2_after_disconnect = create_net(circuit, "L2_after_disconnect", "L2", "L2 after disconnect")
    l3_after_disconnect = create_net(circuit, "L3_after_disconnect", "L3", "L3 after disconnect")
    l1_motor = create_net(circuit, "L1_motor", "L1", "L1 motor side")
    l2_motor = create_net(circuit, "L2_motor", "L2", "L2 motor side")
    l3_motor = create_net(circuit, "L3_motor", "L3", "L3 motor side")
    pe = create_net(circuit, "PE", "PE", "Protective earth")

    connect_source(circuit, l1_source, "L1")
    connect_source(circuit, l2_source, "L2")
    connect_source(circuit, l3_source, "L3")
    connect_source(circuit, pe, "PE")

    attach(circuit, l1_source, terminal(disconnect, "L1"))
    attach(circuit, l2_source, terminal(disconnect, "L2"))
    attach(circuit, l3_source, terminal(disconnect, "L3"))

    attach(circuit, l1_after_disconnect, terminal(disconnect, "T1"))
    attach(circuit, l1_after_disconnect, terminal(starter, "L1"))
    attach(circuit, l1_after_disconnect, terminal(power_supply, "input_L1"))
    connect(circuit, l1_after_disconnect, terminal(disconnect, "T1"), terminal(starter, "L1"))
    connect(circuit, l1_after_disconnect, terminal(disconnect, "T1"), terminal(power_supply, "input_L1"))

    attach(circuit, l2_after_disconnect, terminal(disconnect, "T2"))
    attach(circuit, l2_after_disconnect, terminal(starter, "L2"))
    attach(circuit, l2_after_disconnect, terminal(power_supply, "input_L2"))
    connect(circuit, l2_after_disconnect, terminal(disconnect, "T2"), terminal(starter, "L2"))
    connect(circuit, l2_after_disconnect, terminal(disconnect, "T2"), terminal(power_supply, "input_L2"))

    attach(circuit, l3_after_disconnect, terminal(disconnect, "T3"))
    attach(circuit, l3_after_disconnect, terminal(starter, "L3"))
    connect(circuit, l3_after_disconnect, terminal(disconnect, "T3"), terminal(starter, "L3"))

    attach(circuit, l1_motor, terminal(starter, "T1"))
    attach(circuit, l1_motor, terminal(motor, "T1"))
    connect(circuit, l1_motor, terminal(starter, "T1"), terminal(motor, "T1"))

    attach(circuit, l2_motor, terminal(starter, "T2"))
    attach(circuit, l2_motor, terminal(motor, "T2"))
    connect(circuit, l2_motor, terminal(starter, "T2"), terminal(motor, "T2"))

    attach(circuit, l3_motor, terminal(starter, "T3"))
    attach(circuit, l3_motor, terminal(motor, "T3"))
    connect(circuit, l3_motor, terminal(starter, "T3"), terminal(motor, "T3"))

    attach(circuit, pe, terminal(power_supply, "input_PE"))
    attach(circuit, pe, terminal(motor, "PE"))
    connect(circuit, pe, terminal(power_supply, "input_PE"), terminal(motor, "PE"))


def create_control_connections(circuit: Circuit, power_supply: Component, button: Component, starter: Component) -> None:
    positive_source = create_net(circuit, "+24V_source", "+24V", "+24 VDC source side")
    positive_after_button = create_net(circuit, "+24V_after_button", "+24V", "+24 VDC after start button")
    return_net = create_net(circuit, "0V", "0V", "0 VDC return")
    pe = create_net(circuit, "PE", "PE", "Protective earth")

    connect_source(circuit, positive_source, "+24V")
    connect_source(circuit, return_net, "0V")
    connect_source(circuit, pe, "PE")

    attach(circuit, positive_source, terminal(power_supply, "output_+24V"))
    attach(circuit, positive_source, terminal(button, "IN"))
    connect(circuit, positive_source, terminal(power_supply, "output_+24V"), terminal(button, "IN"))

    attach(circuit, positive_after_button, terminal(button, "OUT"))
    attach(circuit, positive_after_button, terminal(starter, "A1"))
    connect(circuit, positive_after_button, terminal(button, "OUT"), terminal(starter, "A1"))

    attach(circuit, return_net, terminal(starter, "A2"))
    attach(circuit, return_net, terminal(power_supply, "output_0V"))
    connect(circuit, return_net, terminal(starter, "A2"), terminal(power_supply, "output_0V"))


def create_primitive_boundary_examples(system: SchematicSystem) -> None:
    pressure_transmitter = FieldInstrument.objects.create(
        system=system,
        reference="PT-101",
        name="Pump discharge pressure transmitter",
        instrument_kind="pressure_transmitter",
        process_variable="pressure",
        signal_kind="analog_4_20ma",
        metadata={"range": "0-150 psi", "location": "pump discharge"},
    )
    IOPoint.objects.create(
        system=system,
        reference="AI-101",
        name="PT-101 analog input",
        io_kind="analog_input",
        direction=IOPoint.Direction.INPUT,
        signal_kind="analog_4_20ma",
        logical_name="PT101_PV",
        hardware_address="Local:4:I.Ch2Data",
        field_instrument=pressure_transmitter,
    )

    drive = Drive.objects.create(
        system=system,
        reference="VFD-201",
        name="VFD primitive example",
        drive_kind=Drive.DriveKind.VFD,
        metadata={"status": "primitive_example", "note": "Drive primitive is intentionally not collapsed into the starter."},
    )
    drive_io_specs = (
        ("DO-201-RUN", "Run command", "digital_output", IOPoint.Direction.OUTPUT, "discrete_24vdc", "VFD201_RunCmd", "run_command"),
        ("AO-201-SPD", "Speed reference", "analog_output", IOPoint.Direction.OUTPUT, "analog_4_20ma", "VFD201_SpeedRef", "speed_reference"),
        ("DI-201-RUN", "Running status", "digital_input", IOPoint.Direction.INPUT, "discrete_24vdc", "VFD201_Running", "running_status"),
    )
    for sort_order, (reference, name, io_kind, direction, signal_kind, logical_name, function_key) in enumerate(drive_io_specs):
        io_point = IOPoint.objects.create(
            system=system,
            reference=reference,
            name=name,
            io_kind=io_kind,
            direction=direction,
            signal_kind=signal_kind,
            logical_name=logical_name,
        )
        DriveIOPoint.objects.create(drive=drive, io_point=io_point, function_key=function_key, sort_order=sort_order)


def create_potential_nets(circuit: Circuit) -> dict[str, Net]:
    nets = {}
    for circuit_potential in circuit.potentials.select_related("potential_label"):
        nets[circuit_potential.key] = Net.objects.create(
            circuit=circuit,
            key=circuit_potential.key,
            label=circuit_potential.label,
            circuit_potential=circuit_potential,
        )
        SourceConnection.objects.create(
            circuit=circuit,
            net=nets[circuit_potential.key],
            source_terminal=source_terminal(circuit.source, circuit_potential.key),
        )
    return nets


def create_net(circuit: Circuit, key: str, potential_key: str, label: str = "") -> Net:
    return Net.objects.create(
        circuit=circuit,
        key=key,
        label=label or key,
        circuit_potential=circuit.potentials.get(key=potential_key),
    )


def connect_source(circuit: Circuit, net: Net, source_terminal_key: str) -> SourceConnection:
    return SourceConnection.objects.create(
        circuit=circuit,
        net=net,
        source_terminal=source_terminal(circuit.source, source_terminal_key),
    )


def attach(
    circuit: Circuit,
    net: Net,
    attached_terminal: Terminal,
    connection_kind: str = "conductor",
    condition_key: str = "",
) -> NetTerminal:
    return NetTerminal.objects.create(
        circuit=circuit,
        net=net,
        terminal=attached_terminal,
        connection_kind=connection_kind,
        condition_key=condition_key,
    )


def connect(
    circuit: Circuit,
    net: Net,
    from_terminal: Terminal,
    to_terminal: Terminal,
    connection_kind: str = "conductor",
    condition_key: str = "",
) -> Connection:
    return Connection.objects.create(
        circuit=circuit,
        net=net,
        from_terminal=from_terminal,
        to_terminal=to_terminal,
        connection_kind=connection_kind,
        condition_key=condition_key,
    )


def role(component: Component, key: str) -> Role:
    return component.roles.get(key=key)


def terminal(component: Component, key: str) -> Terminal:
    return component.terminals.get(key=key)


def source_terminal(source: Source, key: str) -> SourceTerminal:
    return source.terminals.get(key=key)


def potential_label(potential_system: PotentialSystem, key: str) -> PotentialLabel:
    return potential_system.labels.get(key=key)
