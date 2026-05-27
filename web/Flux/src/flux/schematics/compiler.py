from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Circuit
from .models import Connection
from .models import CompileRun
from .models import DriveIOPoint
from .models import InternalRelation
from .models import NetTerminal
from .models import Role
from .models import RoleContinuity
from .models import RoleTerminal
from .models import SchematicSystem
from .models import Terminal
from .models import TerminalPotentialBinding
from .models import ValidationFinding


MAX_VALIDATION_FINDINGS = 500


@transaction.atomic
def compile_system(system: SchematicSystem) -> CompileRun:
    run = CompileRun.objects.create(system=system, status=CompileRun.Status.RUNNING)
    findings: list[ValidationFinding] = []
    bindings: list[TerminalPotentialBinding] = []
    binding_keys: set[tuple[int, int, int, int, str, str]] = set()

    circuits = system.circuits.select_related("source", "potential_system", "source__potential_system")
    for circuit in circuits:
        compile_circuit(run, circuit, findings, bindings, binding_keys)

    for relation in InternalRelation.objects.filter(component__system=system).select_related(
        "source_role__template__potential_system",
        "target_role__template__potential_system",
    ):
        validate_relation(run, relation, findings)
    validate_kernel_primitives(run, system, findings)

    if findings:
        ValidationFinding.objects.bulk_create(findings[:MAX_VALIDATION_FINDINGS])
    if bindings:
        TerminalPotentialBinding.objects.bulk_create(bindings, ignore_conflicts=True)

    error_count = sum(1 for finding in findings if finding.severity == ValidationFinding.Severity.ERROR)
    run.status = CompileRun.Status.FAILED if error_count else CompileRun.Status.COMPLETE
    run.finding_count = min(len(findings), MAX_VALIDATION_FINDINGS)
    run.binding_count = len(bindings)
    run.summary = {
        "circuits": system.circuits.count(),
        "components": system.components.count(),
        "field_instruments": system.field_instruments.count(),
        "io_points": system.io_points.count(),
        "drives": system.drives.count(),
        "findings": run.finding_count,
        "bindings": run.binding_count,
        "error_count": error_count,
    }
    run.completed_at = timezone.now()
    run.save(update_fields=["status", "finding_count", "binding_count", "summary", "completed_at"])
    return run


def compile_circuit(
    run: CompileRun,
    circuit: Circuit,
    findings: list[ValidationFinding],
    bindings: list[TerminalPotentialBinding],
    binding_keys: set[tuple[int, int, int, int, str, str]],
) -> None:
    if circuit.source.system_id != circuit.system_id:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "source_system_mismatch",
            f"Circuit {circuit.name} source belongs to another schematic system.",
            "circuit",
            circuit.id,
        )
    if circuit.source.potential_system_id != circuit.potential_system_id:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "source_potential_mismatch",
            f"Circuit {circuit.name} source potential system does not match circuit potential system.",
            "circuit",
            circuit.id,
        )
    validate_circuit_source_potentials(run, circuit, findings)

    circuit_potentials = {potential.key: potential for potential in circuit.potentials.all()}
    for participant in circuit.participants.select_related(
        "component",
        "role__template__potential_system",
    ):
        role = participant.role
        role_template = role.template
        if role.component_id != participant.component_id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "participant_role_component_mismatch",
                f"Participant role {role} does not belong to component {participant.component}.",
                "circuit_participant",
                participant.id,
            )
            continue
        if role_template.potential_system_id != circuit.potential_system_id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "role_potential_mismatch",
                f"Role {role} is {role_template.potential_system.key}, not {circuit.potential_system.key}.",
                "role",
                role.id,
            )
            continue

        validate_required_role_terminals(run, role, findings)
        validate_role_continuities(run, role, findings)
        for terminal_link in role.terminal_links.select_related("terminal"):
            if not terminal_link.interface_key:
                continue
            circuit_potential = circuit_potentials.get(terminal_link.interface_key)
            if circuit_potential is None:
                add_finding(
                    run,
                    findings,
                    ValidationFinding.Severity.ERROR,
                    "unknown_role_interface_potential",
                    f"Role {role} references unknown circuit potential {terminal_link.interface_key}.",
                    "role_terminal",
                    terminal_link.id,
                )
                continue
            add_binding(
                run,
                circuit,
                terminal_link.terminal,
                role,
                circuit_potential,
                terminal_condition_key(role, terminal_link),
                "interface",
                {"usage": terminal_link.usage},
                bindings,
                binding_keys,
            )
    validate_and_bind_net_terminals(run, circuit, findings, bindings, binding_keys)
    validate_and_bind_connections(run, circuit, findings, bindings, binding_keys)


def validate_circuit_source_potentials(
    run: CompileRun,
    circuit: Circuit,
    findings: list[ValidationFinding],
) -> None:
    source_potentials = set(circuit.source.potentials.values_list("key", flat=True))
    circuit_potentials = set(circuit.potentials.values_list("key", flat=True))
    if source_potentials != circuit_potentials:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "source_potential_set_mismatch",
            f"Circuit {circuit.name} source potentials do not match circuit potentials.",
            "circuit",
            circuit.id,
        )
    source_terminals = set(circuit.source.terminals.values_list("key", flat=True))
    if source_potentials != source_terminals:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "source_terminal_set_mismatch",
            f"Circuit {circuit.name} source terminals do not match source potentials.",
            "source",
            circuit.source_id,
        )
    validate_source_connections(run, circuit, findings)


def validate_source_connections(
    run: CompileRun,
    circuit: Circuit,
    findings: list[ValidationFinding],
) -> None:
    circuit_potentials = set(circuit.potentials.values_list("key", flat=True))
    connected_potentials: set[str] = set()
    for source_connection in circuit.source_connections.select_related(
        "net__circuit_potential",
        "source_terminal__source",
        "source_terminal__source_potential",
    ):
        if source_connection.source_terminal.source_id != circuit.source_id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "source_connection_source_mismatch",
                f"Source connection {source_connection.id} uses a terminal from another source.",
                "source_connection",
                source_connection.id,
            )
            continue
        if source_connection.net is None or source_connection.net.circuit_potential is None:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "source_connection_without_potential_net",
                f"Source connection {source_connection.id} has no potential-bearing net.",
                "source_connection",
                source_connection.id,
            )
            continue
        if source_connection.net.circuit_id != circuit.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "source_connection_net_circuit_mismatch",
                f"Source connection {source_connection.id} uses a net from another circuit.",
                "source_connection",
                source_connection.id,
            )
            continue
        source_potential_key = source_connection.source_terminal.source_potential.key
        net_potential_key = source_connection.net.circuit_potential.key
        if source_potential_key != net_potential_key:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "source_connection_potential_mismatch",
                f"Source terminal {source_connection.source_terminal} feeds {source_potential_key} but is connected to net {net_potential_key}.",
                "source_connection",
                source_connection.id,
            )
            continue
        connected_potentials.add(net_potential_key)

    missing = sorted(circuit_potentials - connected_potentials)
    if missing:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "missing_source_connection",
            f"Circuit {circuit.name} has unconnected source potentials: {', '.join(missing)}.",
            "circuit",
            circuit.id,
        )


def validate_required_role_terminals(
    run: CompileRun,
    role: Role,
    findings: list[ValidationFinding],
) -> None:
    required_template_keys = set(
        role.template.terminal_links.filter(terminal_template__required=True).values_list("terminal_template__key", flat=True)
    )
    bound_terminal_keys = set(role.terminal_links.values_list("terminal__key", flat=True))
    for missing_key in sorted(required_template_keys - bound_terminal_keys):
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "missing_required_role_terminal",
            f"Role {role} is missing required terminal {missing_key}.",
            "role",
            role.id,
        )


def validate_role_continuities(
    run: CompileRun,
    role: Role,
    findings: list[ValidationFinding],
) -> None:
    role_terminal_by_id = {link.terminal_id: link for link in role.terminal_links.select_related("terminal")}
    for continuity in role.continuities.select_related("from_terminal", "to_terminal"):
        from_link = role_terminal_by_id.get(continuity.from_terminal_id)
        to_link = role_terminal_by_id.get(continuity.to_terminal_id)
        if from_link is None or to_link is None:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "continuity_terminal_not_in_role",
                f"Continuity {continuity.id} references terminals outside role {role}.",
                "role_continuity",
                continuity.id,
            )
            continue
        if continuity.from_terminal.component_id != role.component_id or continuity.to_terminal.component_id != role.component_id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "continuity_terminal_component_mismatch",
                f"Continuity {continuity.id} references a terminal from another component.",
                "role_continuity",
                continuity.id,
            )
            continue
        if from_link.interface_key and to_link.interface_key and from_link.interface_key != to_link.interface_key:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "continuity_potential_mismatch",
                f"Continuity {role} {from_link.terminal.key}->{to_link.terminal.key} crosses {from_link.interface_key} to {to_link.interface_key}.",
                "role_continuity",
                continuity.id,
            )


def validate_and_bind_connections(
    run: CompileRun,
    circuit: Circuit,
    findings: list[ValidationFinding],
    bindings: list[TerminalPotentialBinding],
    binding_keys: set[tuple[int, int, int, int, str, str]],
) -> None:
    for connection in circuit.connections.select_related(
        "net__circuit_potential",
        "from_terminal__component",
        "to_terminal__component",
    ):
        if connection.net is None or connection.net.circuit_potential is None:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "connection_without_potential_net",
                f"Connection {connection.id} has no potential-bearing net.",
                "connection",
                connection.id,
            )
            continue
        if connection.net.circuit_id != circuit.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "connection_net_circuit_mismatch",
                f"Connection {connection.id} uses a net from another circuit.",
                "connection",
                connection.id,
            )
            continue
        validate_and_bind_connection_terminal(
            run,
            circuit,
            connection,
            connection.from_terminal,
            findings,
            bindings,
            binding_keys,
        )
        validate_and_bind_connection_terminal(
            run,
            circuit,
            connection,
            connection.to_terminal,
            findings,
            bindings,
            binding_keys,
        )


def validate_and_bind_connection_terminal(
    run: CompileRun,
    circuit: Circuit,
    connection: Connection,
    terminal: Terminal,
    findings: list[ValidationFinding],
    bindings: list[TerminalPotentialBinding],
    binding_keys: set[tuple[int, int, int, int, str, str]],
) -> None:
    role_links = role_terminal_links_for_circuit_terminal(circuit, terminal)
    if not role_links:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "terminal_not_in_circuit",
            f"Terminal {terminal} is connected in {circuit.name} but has no role in that circuit.",
            "terminal",
            terminal.id,
        )
        return

    net_potential = connection.net.circuit_potential
    for role_link in role_links:
        if role_link.interface_key and role_link.interface_key != net_potential.key:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "net_potential_mismatch",
                f"Terminal {terminal} expects {role_link.interface_key} but is connected to net {net_potential.key}.",
                "connection",
                connection.id,
            )
            continue
        continue


def validate_and_bind_net_terminals(
    run: CompileRun,
    circuit: Circuit,
    findings: list[ValidationFinding],
    bindings: list[TerminalPotentialBinding],
    binding_keys: set[tuple[int, int, int, int, str, str]],
) -> None:
    for net_terminal in circuit.net_terminals.select_related(
        "net__circuit_potential",
        "terminal__component",
    ):
        if net_terminal.net.circuit_id != circuit.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "net_terminal_circuit_mismatch",
                f"Net terminal {net_terminal.id} uses a net from another circuit.",
                "net_terminal",
                net_terminal.id,
            )
            continue
        if net_terminal.net.circuit_potential is None:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "net_terminal_without_potential_net",
                f"Net terminal {net_terminal.id} has no potential-bearing net.",
                "net_terminal",
                net_terminal.id,
            )
            continue
        validate_and_bind_net_terminal(run, circuit, net_terminal, findings, bindings, binding_keys)


def validate_and_bind_net_terminal(
    run: CompileRun,
    circuit: Circuit,
    net_terminal: NetTerminal,
    findings: list[ValidationFinding],
    bindings: list[TerminalPotentialBinding],
    binding_keys: set[tuple[int, int, int, int, str, str]],
) -> None:
    role_links = role_terminal_links_for_circuit_terminal(circuit, net_terminal.terminal)
    if not role_links:
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "terminal_not_in_circuit",
            f"Terminal {net_terminal.terminal} is attached to {net_terminal.net.key} but has no role in {circuit.name}.",
            "net_terminal",
            net_terminal.id,
        )
        return

    net_potential = net_terminal.net.circuit_potential
    for role_link in role_links:
        if role_link.interface_key and role_link.interface_key != net_potential.key:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "net_potential_mismatch",
                f"Terminal {net_terminal.terminal} expects {role_link.interface_key} but is attached to net {net_terminal.net.key} ({net_potential.key}).",
                "net_terminal",
                net_terminal.id,
            )
            continue
        add_binding(
            run,
            circuit,
            net_terminal.terminal,
            role_link.role,
            net_potential,
            net_terminal.condition_key,
            "net",
            {
                "net_id": net_terminal.net_id,
                "net": net_terminal.net.key,
                "connection_kind": net_terminal.connection_kind,
            },
            bindings,
            binding_keys,
        )


def role_terminal_links_for_circuit_terminal(circuit: Circuit, terminal: Terminal) -> list[RoleTerminal]:
    circuit_role_ids = set(circuit.participants.values_list("role_id", flat=True))
    return list(
        terminal.role_links.filter(role_id__in=circuit_role_ids).select_related(
            "role",
            "role__template__potential_system",
        )
    )


def terminal_condition_key(role: Role, terminal_link: RoleTerminal) -> str:
    if role.template.role_kind == "source_output":
        return role.metadata.get("source_condition", "")
    if terminal_link.usage in {"load", "output"}:
        continuity = first_terminal_continuity(role, terminal_link.terminal)
        if continuity is not None:
            return continuity.condition_key
    return ""


def first_terminal_continuity(role: Role, terminal: Terminal) -> RoleContinuity | None:
    return role.continuities.filter(to_terminal=terminal).order_by("sort_order", "id").first()


def add_binding(
    run: CompileRun,
    circuit: Circuit,
    terminal: Terminal,
    role: Role,
    circuit_potential,
    condition_key: str,
    binding_kind: str,
    metadata: dict,
    bindings: list[TerminalPotentialBinding],
    binding_keys: set[tuple[int, int, int, int, str, str]],
) -> None:
    key = (run.id, terminal.id, role.id, circuit_potential.id, condition_key, binding_kind)
    if key in binding_keys:
        return
    binding_keys.add(key)
    bindings.append(
        TerminalPotentialBinding(
            compile_run=run,
            circuit=circuit,
            terminal=terminal,
            role=role,
            circuit_potential=circuit_potential,
            condition_key=condition_key,
            binding_kind=binding_kind,
            metadata=metadata,
        )
    )


def validate_relation(run: CompileRun, relation: InternalRelation, findings: list[ValidationFinding]) -> None:
    source_system_id = relation.source_role.template.potential_system_id
    target_system_id = relation.target_role.template.potential_system_id
    if source_system_id != target_system_id and relation.relation_type != "behavioral":
        add_finding(
            run,
            findings,
            ValidationFinding.Severity.ERROR,
            "cross_circuit_continuity",
            f"Relation {relation.key} crosses potential systems without behavioral isolation.",
            "internal_relation",
            relation.id,
        )


def validate_kernel_primitives(run: CompileRun, system: SchematicSystem, findings: list[ValidationFinding]) -> None:
    for instrument in system.field_instruments.select_related("component"):
        if instrument.component_id and instrument.component.system_id != system.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "field_instrument_component_system_mismatch",
                f"Field instrument {instrument.reference} links to a component from another schematic system.",
                "field_instrument",
                instrument.id,
            )

    for io_point in system.io_points.select_related("field_instrument", "component", "terminal__component"):
        if io_point.field_instrument_id and io_point.field_instrument.system_id != system.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "io_point_field_instrument_system_mismatch",
                f"I/O point {io_point.reference} links to a field instrument from another schematic system.",
                "io_point",
                io_point.id,
            )
        if io_point.component_id and io_point.component.system_id != system.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "io_point_component_system_mismatch",
                f"I/O point {io_point.reference} links to a component from another schematic system.",
                "io_point",
                io_point.id,
            )
        if io_point.terminal_id and io_point.component_id and io_point.terminal.component_id != io_point.component_id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "io_point_terminal_component_mismatch",
                f"I/O point {io_point.reference} terminal does not belong to its component.",
                "io_point",
                io_point.id,
            )

    for drive in system.drives.select_related("component", "driven_component"):
        if drive.component_id and drive.component.system_id != system.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "drive_component_system_mismatch",
                f"Drive {drive.reference} links to a component from another schematic system.",
                "drive",
                drive.id,
            )
        if drive.driven_component_id and drive.driven_component.system_id != system.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "drive_load_component_system_mismatch",
                f"Drive {drive.reference} drives a component from another schematic system.",
                "drive",
                drive.id,
            )

    for drive_io_point in DriveIOPoint.objects.filter(drive__system=system).select_related("drive", "io_point"):
        if drive_io_point.io_point.system_id != system.id:
            add_finding(
                run,
                findings,
                ValidationFinding.Severity.ERROR,
                "drive_io_point_system_mismatch",
                f"Drive {drive_io_point.drive.reference} links to I/O point {drive_io_point.io_point.reference} from another schematic system.",
                "drive_io_point",
                drive_io_point.id,
            )


def add_finding(
    run: CompileRun,
    findings: list[ValidationFinding],
    severity: str,
    code: str,
    message: str,
    object_kind: str = "",
    object_id: int | None = None,
) -> None:
    if len(findings) >= MAX_VALIDATION_FINDINGS:
        return
    findings.append(
        ValidationFinding(
            compile_run=run,
            severity=severity,
            code=code,
            message=message,
            object_kind=object_kind,
            object_id=object_id,
        )
    )
