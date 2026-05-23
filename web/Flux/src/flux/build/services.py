from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from flux_build.targets.ignition_tags import build_ignition_provider
from flux_mine.plc.models import PlcController, PlcDataType, PlcMember, PlcProgram, PlcProject, PlcTag

from flux.mine.models import MineRun

from .models import BuildArtifact, BuildDiagnostic, BuildRun


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
            run.save(update_fields=["status", "output_sha256", "output_bytes", "summary", "completed_at", "updated_at"])
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


def plc_project_from_mine_run(run: MineRun) -> PlcProject:
    controllers: list[PlcController] = []
    controller_rows = run.plc_controllers.prefetch_related("data_types__members", "tags")
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
        global_tags = tuple(plc_tag_from_row(tag_row) for tag_row in tag_rows if tag_row.scope == "Global")
        program_scopes = sorted({tag_row.scope for tag_row in tag_rows if tag_row.scope != "Global"})
        programs = tuple(
            PlcProgram(
                name=scope,
                tags=tuple(plc_tag_from_row(tag_row) for tag_row in tag_rows if tag_row.scope == scope),
            )
            for scope in program_scopes
        )
        controllers.append(
            PlcController(
                name=controller_row.name,
                processor_type=controller_row.processor_type,
                major_version=controller_row.major_version,
                comm_path=controller_row.comm_path,
                data_types=data_types,
                tags=global_tags,
                programs=programs,
                source_path=run.source_path,
                raw=controller_row.raw,
            )
        )
    return PlcProject(controllers=tuple(controllers), source_path=run.source_path, source_sha256=run.source_sha256)


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
