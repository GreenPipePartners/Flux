from __future__ import annotations

from django.db import transaction

from .catalog import ensure_catalog
from .models import Circuit
from .models import CircuitParticipant
from .models import CircuitPotential
from .models import Component
from .models import ComponentTemplate
from .models import Connection
from .models import InternalRelation
from .models import Net
from .models import PotentialLabel
from .models import PotentialSystem
from .models import Role
from .models import RoleTerminal
from .models import SchematicSystem
from .models import Source
from .models import SourcePotential
from .models import Terminal


@transaction.atomic
def build_basic_motor_starter_system() -> SchematicSystem:
    ensure_catalog()
    SchematicSystem.objects.filter(slug="basic-480-motor-starter").delete()
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

    return system


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
        SourcePotential.objects.create(
            source=source,
            potential_label=label,
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
    nets = create_potential_nets(circuit)
    connect(circuit, nets["L1"], terminal(disconnect, "T1"), terminal(starter, "L1"))
    connect(circuit, nets["L2"], terminal(disconnect, "T2"), terminal(starter, "L2"))
    connect(circuit, nets["L3"], terminal(disconnect, "T3"), terminal(starter, "L3"))
    connect(circuit, nets["L1"], terminal(starter, "T1"), terminal(motor, "T1"), "switched_conductor")
    connect(circuit, nets["L2"], terminal(starter, "T2"), terminal(motor, "T2"), "switched_conductor")
    connect(circuit, nets["L3"], terminal(starter, "T3"), terminal(motor, "T3"), "switched_conductor")
    connect(circuit, nets["L1"], terminal(disconnect, "T1"), terminal(power_supply, "input_L1"))
    connect(circuit, nets["L2"], terminal(disconnect, "T2"), terminal(power_supply, "input_L2"))
    connect(circuit, nets["PE"], terminal(power_supply, "input_PE"), terminal(motor, "PE"))


def create_control_connections(circuit: Circuit, power_supply: Component, button: Component, starter: Component) -> None:
    nets = create_potential_nets(circuit)
    connect(circuit, nets["+24V"], terminal(power_supply, "output_+24V"), terminal(button, "IN"))
    connect(circuit, nets["+24V"], terminal(button, "OUT"), terminal(starter, "A1"), "switched_conductor")
    connect(circuit, nets["0V"], terminal(starter, "A2"), terminal(power_supply, "output_0V"))


def create_potential_nets(circuit: Circuit) -> dict[str, Net]:
    nets = {}
    for circuit_potential in circuit.potentials.select_related("potential_label"):
        nets[circuit_potential.key] = Net.objects.create(
            circuit=circuit,
            key=circuit_potential.key,
            label=circuit_potential.label,
            circuit_potential=circuit_potential,
        )
    return nets


def connect(
    circuit: Circuit,
    net: Net,
    from_terminal: Terminal,
    to_terminal: Terminal,
    connection_kind: str = "conductor",
) -> Connection:
    return Connection.objects.create(
        circuit=circuit,
        net=net,
        from_terminal=from_terminal,
        to_terminal=to_terminal,
        connection_kind=connection_kind,
    )


def role(component: Component, key: str) -> Role:
    return component.roles.get(key=key)


def terminal(component: Component, key: str) -> Terminal:
    return component.terminals.get(key=key)


def potential_label(potential_system: PotentialSystem, key: str) -> PotentialLabel:
    return potential_system.labels.get(key=key)
