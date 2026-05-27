from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from .models import ComponentTemplate
from .models import InternalRelationTemplate
from .models import PotentialLabel
from .models import PotentialSystem
from .models import RoleContinuityTemplate
from .models import RoleTemplate
from .models import RoleTerminalTemplate
from .models import TerminalTemplate


@dataclass(frozen=True)
class PotentialLabelSpec:
    key: str
    label: str


@dataclass(frozen=True)
class PotentialSystemSpec:
    key: str
    label: str
    nominal_voltage: str
    phase_count: int
    polarity_kind: str
    description: str
    labels: tuple[PotentialLabelSpec, ...]


@dataclass(frozen=True)
class TerminalSpec:
    key: str
    label: str = ""
    terminal_kind: str = "conductor"
    required: bool = True


@dataclass(frozen=True)
class RoleTerminalSpec:
    terminal_key: str
    interface_key: str = ""
    usage: str = "conductor"


@dataclass(frozen=True)
class RoleContinuitySpec:
    from_terminal_key: str
    to_terminal_key: str
    condition_key: str = ""
    continuity_kind: str = "conductive"


@dataclass(frozen=True)
class RoleSpec:
    key: str
    circuit_kind: str
    role_kind: str
    potential_system_key: str
    label: str = ""
    terminals: tuple[RoleTerminalSpec, ...] = ()
    continuities: tuple[RoleContinuitySpec, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InternalRelationSpec:
    key: str
    source_role_key: str
    target_role_key: str
    condition_key: str
    effect_key: str
    relation_type: str = "behavioral"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentTemplateSpec:
    key: str
    label: str
    component_kind: str
    terminals: tuple[TerminalSpec, ...]
    roles: tuple[RoleSpec, ...]
    relations: tuple[InternalRelationSpec, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def potential_system_specs() -> tuple[PotentialSystemSpec, ...]:
    return (
        PotentialSystemSpec(
            key="480VAC_3PH",
            label="480 VAC 3-phase",
            nominal_voltage="480.00",
            phase_count=3,
            polarity_kind="ac",
            description="Three-phase 480 VAC motor power potential system.",
            labels=(
                PotentialLabelSpec("L1", "Line 1"),
                PotentialLabelSpec("L2", "Line 2"),
                PotentialLabelSpec("L3", "Line 3"),
                PotentialLabelSpec("PE", "Protective earth"),
            ),
        ),
        PotentialSystemSpec(
            key="24VDC_CONTROL",
            label="24 VDC control",
            nominal_voltage="24.00",
            phase_count=1,
            polarity_kind="dc",
            description="24 VDC control potential system.",
            labels=(
                PotentialLabelSpec("+24V", "+24 VDC"),
                PotentialLabelSpec("0V", "0 VDC return"),
                PotentialLabelSpec("PE", "Protective earth"),
            ),
        ),
    )


def component_template_specs() -> tuple[ComponentTemplateSpec, ...]:
    return (
        disconnect_3pole_spec(),
        starter_3pole_24vdc_spec(),
        motor_3phase_spec(),
        power_supply_480_to_24vdc_spec(),
        button_normally_open_spec(),
        button_normally_closed_spec(),
    )


def disconnect_3pole_spec() -> ComponentTemplateSpec:
    return ComponentTemplateSpec(
        key="disconnect_3pole",
        label="3-pole disconnect",
        component_kind="disconnect",
        terminals=_terminals("L1", "L2", "L3", "T1", "T2", "T3"),
        roles=(
            RoleSpec(
                key="isolation_switch_3p",
                label="3-pole isolation switch",
                circuit_kind="power",
                role_kind="isolation_switch",
                potential_system_key="480VAC_3PH",
                terminals=(
                    RoleTerminalSpec("L1", "L1", "line"),
                    RoleTerminalSpec("L2", "L2", "line"),
                    RoleTerminalSpec("L3", "L3", "line"),
                    RoleTerminalSpec("T1", "L1", "load"),
                    RoleTerminalSpec("T2", "L2", "load"),
                    RoleTerminalSpec("T3", "L3", "load"),
                ),
                continuities=(
                    RoleContinuitySpec("L1", "T1", "handle.closed", "switched"),
                    RoleContinuitySpec("L2", "T2", "handle.closed", "switched"),
                    RoleContinuitySpec("L3", "T3", "handle.closed", "switched"),
                ),
            ),
        ),
    )


def starter_3pole_24vdc_spec() -> ComponentTemplateSpec:
    return ComponentTemplateSpec(
        key="starter_3pole_24vdc",
        label="3-pole starter with 24 VDC coil",
        component_kind="starter",
        terminals=_terminals("L1", "L2", "L3", "T1", "T2", "T3", "A1", "A2"),
        roles=(
            RoleSpec(
                key="main_power_contacts",
                label="Main power contacts",
                circuit_kind="power",
                role_kind="switched_contact_3p",
                potential_system_key="480VAC_3PH",
                terminals=(
                    RoleTerminalSpec("L1", "L1", "line"),
                    RoleTerminalSpec("L2", "L2", "line"),
                    RoleTerminalSpec("L3", "L3", "line"),
                    RoleTerminalSpec("T1", "L1", "load"),
                    RoleTerminalSpec("T2", "L2", "load"),
                    RoleTerminalSpec("T3", "L3", "load"),
                ),
                continuities=(
                    RoleContinuitySpec("L1", "T1", "coil.energized", "switched"),
                    RoleContinuitySpec("L2", "T2", "coil.energized", "switched"),
                    RoleContinuitySpec("L3", "T3", "coil.energized", "switched"),
                ),
            ),
            RoleSpec(
                key="coil",
                label="24 VDC coil",
                circuit_kind="control",
                role_kind="coil",
                potential_system_key="24VDC_CONTROL",
                terminals=(
                    RoleTerminalSpec("A1", "+24V", "positive"),
                    RoleTerminalSpec("A2", "0V", "return"),
                ),
                metadata={"state_key": "coil.energized"},
            ),
        ),
        relations=(
            InternalRelationSpec(
                key="coil_energized_closes_main_contacts",
                source_role_key="coil",
                target_role_key="main_power_contacts",
                condition_key="coil.energized",
                effect_key="main_power_contacts.closed",
                metadata={"description": "Control-side coil closes the 480 VAC main contacts."},
            ),
        ),
    )


def motor_3phase_spec() -> ComponentTemplateSpec:
    return ComponentTemplateSpec(
        key="motor_3phase",
        label="3-phase motor",
        component_kind="motor",
        terminals=_terminals("T1", "T2", "T3", "PE"),
        roles=(
            RoleSpec(
                key="three_phase_load",
                label="Three-phase load",
                circuit_kind="power",
                role_kind="load",
                potential_system_key="480VAC_3PH",
                terminals=(
                    RoleTerminalSpec("T1", "L1", "line"),
                    RoleTerminalSpec("T2", "L2", "line"),
                    RoleTerminalSpec("T3", "L3", "line"),
                    RoleTerminalSpec("PE", "PE", "ground"),
                ),
            ),
        ),
    )


def power_supply_480_to_24vdc_spec() -> ComponentTemplateSpec:
    return ComponentTemplateSpec(
        key="power_supply_480_to_24vdc",
        label="480 VAC to 24 VDC power supply",
        component_kind="power_supply",
        terminals=_terminals("input_L1", "input_L2", "input_PE", "output_+24V", "output_0V"),
        roles=(
            RoleSpec(
                key="480_vac_input_load",
                label="480 VAC input load",
                circuit_kind="power",
                role_kind="load",
                potential_system_key="480VAC_3PH",
                terminals=(
                    RoleTerminalSpec("input_L1", "L1", "line"),
                    RoleTerminalSpec("input_L2", "L2", "line"),
                    RoleTerminalSpec("input_PE", "PE", "ground"),
                ),
            ),
            RoleSpec(
                key="24_vdc_source_output",
                label="24 VDC source output",
                circuit_kind="control",
                role_kind="source_output",
                potential_system_key="24VDC_CONTROL",
                terminals=(
                    RoleTerminalSpec("output_+24V", "+24V", "positive"),
                    RoleTerminalSpec("output_0V", "0V", "return"),
                ),
                metadata={"source_condition": "input_power.valid"},
            ),
        ),
        relations=(
            InternalRelationSpec(
                key="valid_input_establishes_24vdc_output",
                source_role_key="480_vac_input_load",
                target_role_key="24_vdc_source_output",
                condition_key="input_power.valid",
                effect_key="output_source.established",
                metadata={"description": "Valid 480 VAC input establishes a separate 24 VDC source."},
            ),
        ),
    )


def button_normally_open_spec() -> ComponentTemplateSpec:
    return ComponentTemplateSpec(
        key="button_no_24vdc",
        label="Normally-open 24 VDC button",
        component_kind="button",
        terminals=_terminals("IN", "OUT"),
        roles=(
            RoleSpec(
                key="normally_open_contact",
                label="Normally-open contact",
                circuit_kind="control",
                role_kind="normally_open_contact",
                potential_system_key="24VDC_CONTROL",
                terminals=(
                    RoleTerminalSpec("IN", "+24V", "line"),
                    RoleTerminalSpec("OUT", "+24V", "load"),
                ),
                continuities=(RoleContinuitySpec("IN", "OUT", "button.pressed", "switched"),),
            ),
        ),
    )


def button_normally_closed_spec() -> ComponentTemplateSpec:
    return ComponentTemplateSpec(
        key="button_nc_24vdc",
        label="Normally-closed 24 VDC button",
        component_kind="button",
        terminals=_terminals("IN", "OUT"),
        roles=(
            RoleSpec(
                key="normally_closed_contact",
                label="Normally-closed contact",
                circuit_kind="control",
                role_kind="normally_closed_contact",
                potential_system_key="24VDC_CONTROL",
                terminals=(
                    RoleTerminalSpec("IN", "+24V", "line"),
                    RoleTerminalSpec("OUT", "+24V", "load"),
                ),
                continuities=(RoleContinuitySpec("IN", "OUT", "button.released", "switched"),),
            ),
        ),
    )


@transaction.atomic
def ensure_catalog() -> None:
    ensure_potential_systems()
    for spec in component_template_specs():
        ensure_component_template(spec)


def ensure_potential_systems() -> dict[str, PotentialSystem]:
    systems: dict[str, PotentialSystem] = {}
    for spec in potential_system_specs():
        potential_system, _created = PotentialSystem.objects.update_or_create(
            key=spec.key,
            defaults={
                "label": spec.label,
                "nominal_voltage": spec.nominal_voltage,
                "phase_count": spec.phase_count,
                "polarity_kind": spec.polarity_kind,
                "description": spec.description,
            },
        )
        systems[spec.key] = potential_system
        for sort_order, label_spec in enumerate(spec.labels):
            PotentialLabel.objects.update_or_create(
                potential_system=potential_system,
                key=label_spec.key,
                defaults={"label": label_spec.label, "sort_order": sort_order},
            )
    return systems


def ensure_component_template(spec: ComponentTemplateSpec) -> ComponentTemplate:
    potential_systems = ensure_potential_systems()
    template, _created = ComponentTemplate.objects.update_or_create(
        key=spec.key,
        defaults={
            "label": spec.label,
            "component_kind": spec.component_kind,
            "metadata": spec.metadata,
        },
    )

    terminal_templates: dict[str, TerminalTemplate] = {}
    for sort_order, terminal_spec in enumerate(spec.terminals):
        terminal_template, _created = TerminalTemplate.objects.update_or_create(
            component_template=template,
            key=terminal_spec.key,
            defaults={
                "label": terminal_spec.label or terminal_spec.key,
                "terminal_kind": terminal_spec.terminal_kind,
                "required": terminal_spec.required,
                "sort_order": sort_order,
            },
        )
        terminal_templates[terminal_spec.key] = terminal_template

    role_templates: dict[str, RoleTemplate] = {}
    for role_spec in spec.roles:
        role_template, _created = RoleTemplate.objects.update_or_create(
            component_template=template,
            key=role_spec.key,
            defaults={
                "label": role_spec.label or role_spec.key,
                "circuit_kind": role_spec.circuit_kind,
                "role_kind": role_spec.role_kind,
                "potential_system": potential_systems[role_spec.potential_system_key],
                "metadata": role_spec.metadata,
            },
        )
        role_templates[role_spec.key] = role_template
        for sort_order, role_terminal_spec in enumerate(role_spec.terminals):
            RoleTerminalTemplate.objects.update_or_create(
                role_template=role_template,
                terminal_template=terminal_templates[role_terminal_spec.terminal_key],
                defaults={
                    "interface_key": role_terminal_spec.interface_key,
                    "usage": role_terminal_spec.usage,
                    "sort_order": sort_order,
                },
            )
        for sort_order, continuity_spec in enumerate(role_spec.continuities):
            RoleContinuityTemplate.objects.update_or_create(
                role_template=role_template,
                from_terminal_template=terminal_templates[continuity_spec.from_terminal_key],
                to_terminal_template=terminal_templates[continuity_spec.to_terminal_key],
                condition_key=continuity_spec.condition_key,
                defaults={
                    "continuity_kind": continuity_spec.continuity_kind,
                    "sort_order": sort_order,
                },
            )

    for relation_spec in spec.relations:
        InternalRelationTemplate.objects.update_or_create(
            component_template=template,
            key=relation_spec.key,
            defaults={
                "relation_type": relation_spec.relation_type,
                "source_role_template": role_templates[relation_spec.source_role_key],
                "target_role_template": role_templates[relation_spec.target_role_key],
                "condition_key": relation_spec.condition_key,
                "effect_key": relation_spec.effect_key,
                "metadata": relation_spec.metadata,
            },
        )

    return template


def _terminals(*keys: str) -> tuple[TerminalSpec, ...]:
    return tuple(TerminalSpec(key=key, label=key) for key in keys)
