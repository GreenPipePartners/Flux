from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Circuit
from .models import CompileRun
from .models import InternalRelation
from .models import SchematicSystem
from .models import TerminalPotentialBinding
from .models import ValidationFinding


MAX_VALIDATION_FINDINGS = 500


@transaction.atomic
def compile_system(system: SchematicSystem) -> CompileRun:
    run = CompileRun.objects.create(system=system, status=CompileRun.Status.RUNNING)
    findings: list[ValidationFinding] = []
    bindings: list[TerminalPotentialBinding] = []

    circuits = system.circuits.select_related("source", "potential_system", "source__potential_system")
    for circuit in circuits:
        compile_circuit(run, circuit, findings, bindings)

    for relation in InternalRelation.objects.filter(component__system=system).select_related(
        "source_role__template__potential_system",
        "target_role__template__potential_system",
    ):
        validate_relation(run, relation, findings)

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
) -> None:
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

        condition_key = role.metadata.get("continuity_condition", "")
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
            bindings.append(
                TerminalPotentialBinding(
                    compile_run=run,
                    circuit=circuit,
                    terminal=terminal_link.terminal,
                    role=role,
                    circuit_potential=circuit_potential,
                    condition_key=condition_key,
                    binding_kind="interface",
                    metadata={"usage": terminal_link.usage},
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
