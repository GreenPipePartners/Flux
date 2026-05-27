from __future__ import annotations

from .models import CompileRun


def compile_run_diagnostic_payload(run: CompileRun) -> dict:
    system = run.system
    return {
        "system": {
            "id": system.id,
            "name": system.name,
            "slug": system.slug,
        },
        "compile_run": {
            "id": run.id,
            "status": run.status,
            "finding_count": run.finding_count,
            "binding_count": run.binding_count,
            "summary": run.summary,
        },
        "counts": {
            "sources": system.sources.count(),
            "circuits": system.circuits.count(),
            "components": system.components.count(),
            "field_instruments": system.field_instruments.count(),
            "io_points": system.io_points.count(),
            "drives": system.drives.count(),
        },
        "sources": source_payloads(system),
        "circuits": circuit_payloads(system),
        "components": component_payloads(system),
        "field_instruments": field_instrument_payloads(system),
        "io_points": io_point_payloads(system),
        "drives": drive_payloads(system),
        "terminal_bindings": terminal_binding_payloads(run),
        "findings": finding_payloads(run),
    }


def source_payloads(system) -> list[dict]:
    return [
        {
            "name": source.name,
            "kind": source.source_kind,
            "potential_system": source.potential_system.key,
            "producer_component": source.producer_component.reference if source.producer_component_id else "",
            "producer_role": source.producer_role.key if source.producer_role_id else "",
            "potentials": list(source.potentials.order_by("sort_order", "key").values_list("key", flat=True)),
            "terminals": [
                {
                    "key": terminal.key,
                    "potential": terminal.source_potential.key,
                }
                for terminal in source.terminals.select_related("source_potential").order_by("sort_order", "key")
            ],
        }
        for source in system.sources.select_related("potential_system", "producer_component", "producer_role").order_by("name")
    ]


def circuit_payloads(system) -> list[dict]:
    circuits = system.circuits.select_related("source", "potential_system").order_by("sort_order", "name")
    return [
        {
            "name": circuit.name,
            "kind": circuit.circuit_kind,
            "source": circuit.source.name,
            "potential_system": circuit.potential_system.key,
            "potentials": list(circuit.potentials.order_by("sort_order", "key").values_list("key", flat=True)),
            "source_connections": [
                {
                    "source_terminal": source_connection.source_terminal.key,
                    "net": source_connection.net.key if source_connection.net_id else "",
                    "potential": source_connection.net.circuit_potential.key
                    if source_connection.net_id and source_connection.net.circuit_potential_id
                    else "",
                    "condition": source_connection.condition_key,
                }
                for source_connection in circuit.source_connections.select_related(
                    "source_terminal",
                    "net",
                    "net__circuit_potential",
                ).order_by("source_terminal__sort_order", "source_terminal__key")
            ],
            "participants": [
                {
                    "component": participant.component.reference,
                    "role": participant.role.key,
                    "role_kind": participant.role.template.role_kind,
                }
                for participant in circuit.participants.select_related("component", "role", "role__template").order_by(
                    "sort_order",
                    "component__reference",
                )
            ],
        }
        for circuit in circuits
    ]


def component_payloads(system) -> list[dict]:
    components = system.components.select_related("template").order_by("reference")
    return [
        {
            "reference": component.reference,
            "name": component.name,
            "template": component.template.key,
            "kind": component.template.component_kind,
            "terminals": list(component.terminals.order_by("template__sort_order", "key").values_list("key", flat=True)),
            "roles": role_payloads(component),
        }
        for component in components
    ]


def field_instrument_payloads(system) -> list[dict]:
    instruments = system.field_instruments.select_related("component").order_by("reference")
    return [
        {
            "reference": instrument.reference,
            "name": instrument.name,
            "instrument_kind": instrument.instrument_kind,
            "process_variable": instrument.process_variable,
            "signal_kind": instrument.signal_kind,
            "component": instrument.component.reference if instrument.component_id else "",
            "metadata": instrument.metadata,
        }
        for instrument in instruments
    ]


def io_point_payloads(system) -> list[dict]:
    io_points = system.io_points.select_related("field_instrument", "component", "terminal").order_by("reference")
    return [
        {
            "reference": io_point.reference,
            "name": io_point.name,
            "io_kind": io_point.io_kind,
            "direction": io_point.direction,
            "signal_kind": io_point.signal_kind,
            "logical_name": io_point.logical_name,
            "hardware_address": io_point.hardware_address,
            "field_instrument": io_point.field_instrument.reference if io_point.field_instrument_id else "",
            "component": io_point.component.reference if io_point.component_id else "",
            "terminal": io_point.terminal.key if io_point.terminal_id else "",
            "metadata": io_point.metadata,
        }
        for io_point in io_points
    ]


def drive_payloads(system) -> list[dict]:
    drives = system.drives.select_related("component", "driven_component").order_by("reference")
    return [
        {
            "reference": drive.reference,
            "name": drive.name,
            "drive_kind": drive.drive_kind,
            "component": drive.component.reference if drive.component_id else "",
            "driven_component": drive.driven_component.reference if drive.driven_component_id else "",
            "io_points": [
                {
                    "reference": link.io_point.reference,
                    "function": link.function_key,
                    "direction": link.io_point.direction,
                    "signal_kind": link.io_point.signal_kind,
                }
                for link in drive.io_links.select_related("io_point").order_by("sort_order", "function_key")
            ],
            "metadata": drive.metadata,
        }
        for drive in drives
    ]


def role_payloads(component) -> list[dict]:
    roles = component.roles.select_related("template", "template__potential_system").order_by("key")
    return [
        {
            "key": role.key,
            "kind": role.template.role_kind,
            "circuit_kind": role.template.circuit_kind,
            "potential_system": role.template.potential_system.key,
            "terminals": [
                {
                    "terminal": link.terminal.key,
                    "interface": link.interface_key,
                    "usage": link.usage,
                }
                for link in role.terminal_links.select_related("terminal").order_by("sort_order", "terminal__key")
            ],
            "continuities": [
                {
                    "from": continuity.from_terminal.key,
                    "to": continuity.to_terminal.key,
                    "condition": continuity.condition_key,
                    "kind": continuity.continuity_kind,
                }
                for continuity in role.continuities.select_related("from_terminal", "to_terminal").order_by(
                    "sort_order",
                    "from_terminal__key",
                    "to_terminal__key",
                )
            ],
        }
        for role in roles
    ]


def terminal_binding_payloads(run: CompileRun) -> list[dict]:
    bindings = run.terminal_bindings.select_related(
        "circuit",
        "role",
        "terminal__component",
        "circuit_potential",
    ).order_by("circuit__sort_order", "terminal__component__reference", "terminal__key", "binding_kind")
    return [
        {
            "circuit": binding.circuit.name,
            "component": binding.terminal.component.reference,
            "terminal": binding.terminal.key,
            "role": binding.role.key,
            "potential": binding.circuit_potential.key,
            "condition": binding.condition_key,
            "kind": binding.binding_kind,
            "metadata": binding.metadata,
        }
        for binding in bindings
    ]


def finding_payloads(run: CompileRun) -> list[dict]:
    return [
        {
            "severity": finding.severity,
            "code": finding.code,
            "message": finding.message,
            "object_kind": finding.object_kind,
            "object_id": finding.object_id,
        }
        for finding in run.findings.order_by("severity", "code", "id")
    ]
