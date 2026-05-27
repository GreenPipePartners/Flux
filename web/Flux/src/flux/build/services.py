from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from flux_build.hmi.models import HmiMapComponent, HmiMapProject, HmiMapScreen, HmiMapTagReference
from flux_build.hmi.symbolic import build_symbolic_hmi_map
from flux_build.targets.ignition_tags import build_ignition_provider
from flux_build.targets.logix_l5k import build_logix_l5k
from flux_build.targets.logix_l5x import build_logix_l5x
from flux_mine.plc.l5k import parse_l5k_text
from flux_mine.plc.models import (
    PlcController,
    PlcDataType,
    PlcInstruction,
    PlcInstructionTagReference,
    PlcMember,
    PlcProgram,
    PlcProject,
    PlcRoutine,
    PlcRung,
    PlcTask,
    PlcTag,
)
from flux_mine.plc.l5x import parse_l5x_text

from flux.mine.models import MineRun
from flux.mine.services import mine_factorytalk_sqlite_export

from .models import BuildArtifact, BuildDiagnostic, BuildRun, HmiMapSelection


SAMPLE_HMI_DEMO_LABEL = "Demo HMI SQLite sample"
SAMPLE_HMI_DEMO_RELATIVE_PATH = Path("local_hmi_sqlite_export") / "conversion_data.sqlite3"


def build_ignition_tags_from_mine_run(mine_run_id: int, output_path: str | Path) -> BuildRun:
    mine_run = MineRun.objects.get(pk=mine_run_id)
    run = BuildRun.objects.create(
        mine_run=mine_run,
        target=BuildRun.Target.IGNITION_TAGS,
        status=BuildRun.Status.RUNNING,
        output_path=str(output_path),
    )
    try:
        project = plc_project_from_mine_run(mine_run)
        if not project.controllers:
            raise ValueError("Ignition tag builds require a PLC mine run")
        result = build_ignition_provider(project)
        payload = json.dumps(result.provider, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        artifact_path = Path(output_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        with transaction.atomic():
            run.status = BuildRun.Status.COMPLETE
            run.output_sha256 = digest
            run.output_bytes = len(payload)
            run.summary = {
                "controller_count": len(project.controllers),
                "top_level_tag_count": len(result.provider.get("tags", [])),
                "diagnostic_count": len(result.diagnostics),
            }
            run.completed_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "output_sha256",
                    "output_bytes",
                    "summary",
                    "completed_at",
                    "updated_at",
                ]
            )
            BuildArtifact.objects.create(
                run=run,
                kind="ignition_provider_json",
                path=str(artifact_path),
                sha256=digest,
                size_bytes=len(payload),
            )
            BuildDiagnostic.objects.bulk_create(
                [
                    BuildDiagnostic(
                        run=run,
                        severity=diagnostic.severity,
                        code=diagnostic.code,
                        message=diagnostic.message,
                        context=diagnostic.context,
                    )
                    for diagnostic in result.diagnostics
                ]
            )
    except Exception as exc:
        run.status = BuildRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


def build_logix_l5x_from_mine_run(mine_run_id: int, output_path: str | Path) -> BuildRun:
    mine_run = MineRun.objects.get(pk=mine_run_id)
    run = BuildRun.objects.create(
        mine_run=mine_run,
        target=BuildRun.Target.LOGIX_L5X,
        status=BuildRun.Status.RUNNING,
        output_path=str(output_path),
    )
    try:
        project = plc_project_from_mine_run(mine_run)
        if not project.controllers:
            raise ValueError("Logix L5X builds require a PLC mine run")
        payload = build_logix_l5x(project)
        generated_project = parse_l5x_text(
            payload.decode("utf-8"),
            source_path=str(output_path),
            source_sha256=hashlib.sha256(payload).hexdigest(),
        )
        original_counts = plc_project_counts(project)
        generated_counts = plc_project_counts(generated_project)
        if generated_counts != original_counts:
            raise ValueError(
                "Generated L5X parse-back counts diverged: original=%s generated=%s"
                % (original_counts, generated_counts)
            )

        artifact_path = Path(output_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        with transaction.atomic():
            run.status = BuildRun.Status.COMPLETE
            run.output_sha256 = digest
            run.output_bytes = len(payload)
            run.summary = {
                **original_counts,
                "round_trip": {
                    "parser": "l5x",
                    "counts_match": True,
                    "generated_counts": generated_counts,
                },
            }
            run.completed_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "output_sha256",
                    "output_bytes",
                    "summary",
                    "completed_at",
                    "updated_at",
                ]
            )
            BuildArtifact.objects.create(
                run=run,
                kind="logix_l5x",
                path=str(artifact_path),
                sha256=digest,
                size_bytes=len(payload),
            )
    except Exception as exc:
        run.status = BuildRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


def build_logix_l5k_from_mine_run(mine_run_id: int, output_path: str | Path) -> BuildRun:
    mine_run = MineRun.objects.get(pk=mine_run_id)
    run = BuildRun.objects.create(
        mine_run=mine_run,
        target=BuildRun.Target.LOGIX_L5K,
        status=BuildRun.Status.RUNNING,
        output_path=str(output_path),
    )
    try:
        project = plc_project_from_mine_run(mine_run)
        if not project.controllers:
            raise ValueError("Logix L5K builds require a PLC mine run")
        payload = build_logix_l5k(project)
        digest = hashlib.sha256(payload).hexdigest()
        generated_project = parse_l5k_text(
            payload.decode("utf-8"),
            source_path=str(output_path),
            source_sha256=digest,
        )
        original_counts = plc_project_counts(project)
        generated_counts = plc_project_counts(generated_project)
        if generated_counts != original_counts:
            raise ValueError(
                "Generated L5K parse-back counts diverged: original=%s generated=%s"
                % (original_counts, generated_counts)
            )

        artifact_path = Path(output_path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(payload)
        with transaction.atomic():
            run.status = BuildRun.Status.COMPLETE
            run.output_sha256 = digest
            run.output_bytes = len(payload)
            run.summary = {
                **original_counts,
                "round_trip": {
                    "parser": "l5k",
                    "counts_match": True,
                    "generated_counts": generated_counts,
                },
            }
            run.completed_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "output_sha256",
                    "output_bytes",
                    "summary",
                    "completed_at",
                    "updated_at",
                ]
            )
            BuildArtifact.objects.create(
                run=run,
                kind="logix_l5k",
                path=str(artifact_path),
                sha256=digest,
                size_bytes=len(payload),
            )
    except Exception as exc:
        run.status = BuildRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


def plc_project_from_mine_run(run: MineRun) -> PlcProject:
    controllers: list[PlcController] = []
    controller_rows = run.plc_controllers.prefetch_related(
        "data_types__members",
        "tags",
        "programs__routines__rungs__instructions__tag_references",
        "tasks__scheduled_programs",
    )
    for controller_row in controller_rows:
        data_types = tuple(
            PlcDataType(
                name=data_type_row.name,
                description=data_type_row.description,
                is_aoi=data_type_row.is_aoi,
                members=tuple(
                    PlcMember(
                        name=member_row.name,
                        data_type=member_row.data_type_name,
                        array_dimensions=tuple(member_row.array_dimensions or []),
                        hidden=member_row.hidden,
                        description=member_row.description,
                        target=member_row.target,
                        bit_number=member_row.bit_number,
                        external_access=member_row.external_access,
                        usage=member_row.usage,
                        required=member_row.required,
                        visible=member_row.visible,
                        constant=member_row.constant,
                        radix=member_row.radix,
                        raw=member_row.raw,
                    )
                    for member_row in data_type_row.members.all()
                ),
                raw=data_type_row.raw,
            )
            for data_type_row in controller_row.data_types.all()
        )
        tag_rows = list(controller_row.tags.all())
        global_tags = tuple(
            plc_tag_from_row(tag_row) for tag_row in tag_rows if tag_row.scope == "Global"
        )
        program_rows = list(controller_row.programs.all())
        if program_rows:
            programs = tuple(plc_program_from_row(program_row, tag_rows) for program_row in program_rows)
        else:
            program_scopes = sorted({tag_row.scope for tag_row in tag_rows if tag_row.scope != "Global"})
            programs = tuple(
                PlcProgram(
                    name=scope,
                    tags=tuple(plc_tag_from_row(tag_row) for tag_row in tag_rows if tag_row.scope == scope),
                )
                for scope in program_scopes
            )
        tasks = tuple(plc_task_from_row(task_row) for task_row in controller_row.tasks.all())
        controllers.append(
            PlcController(
                name=controller_row.name,
                processor_type=controller_row.processor_type,
                major_version=controller_row.major_version,
                comm_path=controller_row.comm_path,
                data_types=data_types,
                tags=global_tags,
                programs=programs,
                tasks=tasks,
                source_path=run.source_path,
                raw=controller_row.raw,
            )
        )
    return PlcProject(
        controllers=tuple(controllers), source_path=run.source_path, source_sha256=run.source_sha256
    )


def plc_tag_from_row(tag_row) -> PlcTag:
    return PlcTag(
        name=tag_row.name,
        data_type=tag_row.data_type_name,
        scope=tag_row.scope,
        tag_type=tag_row.tag_type,
        array_dimensions=tuple(tag_row.array_dimensions or []),
        alias_for=tag_row.alias_for,
        hidden=tag_row.hidden,
        description=tag_row.description,
        external_access=tag_row.external_access,
        constant=tag_row.constant,
        radix=tag_row.radix,
        raw=tag_row.raw,
    )


def plc_program_from_row(program_row, tag_rows) -> PlcProgram:
    return PlcProgram(
        name=program_row.name,
        main_routine_name=program_row.main_routine_name,
        tags=tuple(plc_tag_from_row(tag_row) for tag_row in tag_rows if tag_row.scope == program_row.name),
        routines=tuple(plc_routine_from_row(routine_row) for routine_row in program_row.routines.all()),
        raw=program_row.raw,
    )


def plc_routine_from_row(routine_row) -> PlcRoutine:
    return PlcRoutine(
        name=routine_row.name,
        routine_type=routine_row.routine_type,
        rungs=tuple(plc_rung_from_row(rung_row) for rung_row in routine_row.rungs.all()),
        raw=routine_row.raw,
    )


def plc_rung_from_row(rung_row) -> PlcRung:
    return PlcRung(
        number=rung_row.number,
        rung_type=rung_row.rung_type,
        text=rung_row.text,
        comment=rung_row.comment,
        instructions=tuple(plc_instruction_from_row(instruction_row) for instruction_row in rung_row.instructions.all()),
        raw=rung_row.raw,
    )


def plc_instruction_from_row(instruction_row) -> PlcInstruction:
    return PlcInstruction(
        mnemonic=instruction_row.mnemonic,
        operands=tuple(instruction_row.operands or []),
        tag_references=tuple(
            PlcInstructionTagReference(
                original=reference_row.original,
                base_tag=reference_row.base_tag,
                member_path=reference_row.member_path,
                operand_index=reference_row.operand_index,
                role=reference_row.role,
                raw=reference_row.raw,
            )
            for reference_row in instruction_row.tag_references.all()
        ),
        raw=instruction_row.raw,
    )


def plc_task_from_row(task_row) -> PlcTask:
    return PlcTask(
        name=task_row.name,
        task_type=task_row.task_type,
        priority=task_row.priority,
        rate=task_row.rate,
        watchdog=task_row.watchdog,
        disable_update_outputs=task_row.disable_update_outputs,
        inhibit_task=task_row.inhibit_task,
        scheduled_programs=tuple(link.name for link in task_row.scheduled_programs.all()),
        raw=task_row.raw,
    )


def plc_project_counts(project: PlcProject) -> dict[str, int]:
    return {
        "controller_count": len(project.controllers),
        "global_tag_count": sum(len(controller.tags) for controller in project.controllers),
        "program_count": sum(len(controller.programs) for controller in project.controllers),
        "program_tag_count": sum(len(program.tags) for controller in project.controllers for program in controller.programs),
        "task_count": sum(len(controller.tasks) for controller in project.controllers),
        "scheduled_program_count": sum(len(task.scheduled_programs) for controller in project.controllers for task in controller.tasks),
        "routine_count": sum(len(program.routines) for controller in project.controllers for program in controller.programs),
        "rung_count": sum(
            len(routine.rungs)
            for controller in project.controllers
            for program in controller.programs
            for routine in program.routines
        ),
        "instruction_count": sum(
            len(rung.instructions)
            for controller in project.controllers
            for program in controller.programs
            for routine in program.routines
            for rung in routine.rungs
        ),
        "tag_reference_count": sum(
            len(instruction.tag_references)
            for controller in project.controllers
            for program in controller.programs
            for routine in program.routines
            for rung in routine.rungs
            for instruction in rung.instructions
        ),
    }


def build_hmi_symbolic_map_from_mine_run(mine_run_id: int, output_dir: str | Path) -> BuildRun:
    mine_run = MineRun.objects.get(pk=mine_run_id)
    run = BuildRun.objects.create(
        mine_run=mine_run,
        target=BuildRun.Target.HMI_SYMBOLIC_MAP,
        status=BuildRun.Status.RUNNING,
        output_path=str(output_dir),
    )
    try:
        project = hmi_map_project_from_mine_run(mine_run)
        if not project.screens:
            raise ValueError("HMI symbolic map builds require an HMI mine run")
        result = build_symbolic_hmi_map(project)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        json_payload = (
            json.dumps(result.as_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
        )
        json_path = output_path / "hmi_map.json"
        json_path.write_bytes(json_payload)
        artifacts = [artifact_row(run, "hmi_symbolic_map_json", json_path, json_payload)]

        screens_dir = output_path / "screens"
        screens_dir.mkdir(exist_ok=True)
        for screen_key, svg in result.svg_by_screen.items():
            svg_payload = svg.encode("utf-8") + b"\n"
            svg_path = screens_dir / f"{safe_filename(screen_key)}.svg"
            svg_path.write_bytes(svg_payload)
            artifacts.append(artifact_row(run, "hmi_symbolic_map_svg", svg_path, svg_payload))

        with transaction.atomic():
            run.status = BuildRun.Status.COMPLETE
            run.output_sha256 = hashlib.sha256(json_payload).hexdigest()
            run.output_bytes = sum(artifact.size_bytes for artifact in artifacts)
            run.summary = {
                "screen_count": len(result.project.screens),
                "component_count": sum(len(screen.components) for screen in result.project.screens),
                "artifact_count": len(artifacts),
                "diagnostic_count": len(result.diagnostics),
            }
            run.completed_at = timezone.now()
            run.save(
                update_fields=[
                    "status",
                    "output_sha256",
                    "output_bytes",
                    "summary",
                    "completed_at",
                    "updated_at",
                ]
            )
            BuildArtifact.objects.bulk_create(artifacts)
            BuildDiagnostic.objects.bulk_create(
                [
                    BuildDiagnostic(
                        run=run,
                        severity=diagnostic.severity,
                        code=diagnostic.code,
                        message=diagnostic.message,
                        context=diagnostic.context,
                    )
                    for diagnostic in result.diagnostics
                ]
            )
    except Exception as exc:
        run.status = BuildRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


def seed_hmi_demo_build_sample(
    *,
    sqlite_path: str | Path | None = None,
    max_display_screens: int | None = 8,
    output_dir: str | Path = "/tmp/opencode/flux-build-hmi-demo",
    replace: bool = True,
) -> BuildRun:
    source_path = Path(sqlite_path) if sqlite_path is not None else default_hmi_demo_sqlite_path()
    if not source_path.exists():
        raise FileNotFoundError(f"HMI demo SQLite sample not found: {source_path}")
    if replace:
        sample_runs = MineRun.objects.filter(label=SAMPLE_HMI_DEMO_LABEL, source_path=str(source_path))
        BuildRun.objects.filter(mine_run__in=sample_runs).delete()
        sample_runs.delete()
    mine_run = mine_factorytalk_sqlite_export(
        source_path,
        label=SAMPLE_HMI_DEMO_LABEL,
        max_display_screens=max_display_screens,
    )
    return build_hmi_symbolic_map_from_mine_run(mine_run.id, output_dir)


def default_hmi_demo_sqlite_path() -> Path:
    return settings.REPO_ROOT / SAMPLE_HMI_DEMO_RELATIVE_PATH


def hmi_map_project_from_mine_run(run: MineRun) -> HmiMapProject:
    selected_component_ids = selected_hmi_component_ids(run)
    screens: list[HmiMapScreen] = []
    screen_rows = run.hmi_screens.prefetch_related("components__tag_references")
    for screen_row in screen_rows:
        components: list[HmiMapComponent] = []
        for component_row in screen_row.components.all():
            if (
                selected_component_ids is not None
                and component_row.id not in selected_component_ids
            ):
                continue
            references = deduped_hmi_map_references(component_row.tag_references.all())
            if not references:
                continue
            components.append(
                HmiMapComponent(
                    component_key=component_row.component_path or str(component_row.id),
                    parent_key=component_row.parent_path,
                    name=component_row.name,
                    vendor_type=component_row.component_type,
                    bounds=component_row.bounds,
                    tag_references=references,
                    global_object_reference=component_row.global_object_reference,
                    raw={
                        "source_component_id": component_row.id,
                        "is_group": component_row.is_group,
                        "is_global_instance": component_row.is_global_instance,
                        "geometry": component_row.geometry,
                    },
                )
            )
        if components:
            screens.append(
                HmiMapScreen(
                    screen_key=screen_row.source_path or screen_row.name,
                    name=screen_row.name,
                    source_path=screen_row.source_path,
                    screen_type=screen_row.screen_type,
                    width=screen_row.width,
                    height=screen_row.height,
                    components=tuple(components),
                )
            )
    return HmiMapProject(
        screens=tuple(screens), source_path=run.source_path, source_sha256=run.source_sha256
    )


def selected_hmi_component_ids(run: MineRun) -> set[int] | None:
    selections = HmiMapSelection.objects.filter(mine_run=run, component__isnull=False)
    if not selections.exists():
        return None
    return set(selections.filter(enabled=True).values_list("component_id", flat=True))


def deduped_hmi_map_references(reference_rows) -> tuple[HmiMapTagReference, ...]:
    references: list[HmiMapTagReference] = []
    seen: set[str] = set()
    for row in reference_rows:
        if row.original in seen:
            continue
        seen.add(row.original)
        references.append(
            HmiMapTagReference(
                original=row.original,
                shortcut=row.shortcut,
                scope=row.scope,
                base_tag=row.base_tag,
                member_path=row.member_path,
                raw_tag_path=row.raw_tag_path,
            )
        )
    return tuple(references)


def artifact_row(run: BuildRun, kind: str, path: Path, payload: bytes) -> BuildArtifact:
    return BuildArtifact(
        run=run,
        kind=kind,
        path=str(path),
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return cleaned.strip("_") or "screen"
