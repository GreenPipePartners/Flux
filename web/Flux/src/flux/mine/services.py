from __future__ import annotations

from pathlib import Path

from django.db import transaction
from django.utils import timezone

from flux_mine.hmi.factorytalk import FactoryTalkProject, parse_factorytalk_path
from flux_mine.plc.models import PlcProject
from flux_mine.plc.parsers import parse_plc_file

from .models import (
    HmiComponentFact,
    HmiParameterFact,
    HmiParameterFileFact,
    HmiScreenFact,
    HmiTagReferenceFact,
    MineRun,
    PlcControllerFact,
    PlcDataTypeFact,
    PlcMemberFact,
    PlcTagFact,
)


def mine_source(path: str | Path, *, source_type: str = "auto", label: str = "") -> MineRun:
    source_path = Path(path)
    resolved_type = resolve_source_type(source_path, source_type)
    run = MineRun.objects.create(
        label=label or source_path.name,
        source_type=resolved_type,
        source_path=str(source_path),
        status=MineRun.Status.RUNNING,
    )
    try:
        if resolved_type in {MineRun.SourceType.PLC_L5X, MineRun.SourceType.PLC_L5K}:
            project = parse_plc_file(source_path)
            persist_plc_project(run, project)
        elif resolved_type == MineRun.SourceType.FACTORYTALK:
            project = parse_factorytalk_path(source_path)
            persist_factorytalk_project(run, project)
        else:
            raise ValueError(f"Unsupported mine source type: {resolved_type}")
    except Exception as exc:
        run.status = MineRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


def resolve_source_type(path: Path, source_type: str) -> str:
    normalized = source_type.lower()
    if normalized in {MineRun.SourceType.PLC_L5X, MineRun.SourceType.PLC_L5K, MineRun.SourceType.FACTORYTALK}:
        return normalized
    if normalized == "plc":
        if path.suffix.lower() == ".l5x":
            return MineRun.SourceType.PLC_L5X
        if path.suffix.lower() == ".l5k":
            return MineRun.SourceType.PLC_L5K
        raise ValueError("PLC mining requires an .L5X or .L5K source file")
    if normalized != "auto":
        raise ValueError(f"Unknown mine source type: {source_type}")
    if path.is_dir() or path.suffix.lower() in {".xml", ".par"}:
        return MineRun.SourceType.FACTORYTALK
    if path.suffix.lower() == ".l5x":
        return MineRun.SourceType.PLC_L5X
    if path.suffix.lower() == ".l5k":
        return MineRun.SourceType.PLC_L5K
    raise ValueError(f"Could not infer mine source type from: {path}")


@transaction.atomic
def persist_plc_project(run: MineRun, project: PlcProject) -> MineRun:
    run.source_sha256 = project.source_sha256
    run.summary = project.summary()
    run.status = MineRun.Status.COMPLETE
    run.completed_at = timezone.now()
    run.save(update_fields=["source_sha256", "summary", "status", "completed_at", "updated_at"])

    for controller in project.controllers:
        controller_fact = PlcControllerFact.objects.create(
            run=run,
            name=controller.name,
            processor_type=controller.processor_type,
            major_version=controller.major_version,
            comm_path=controller.comm_path,
            data_type_count=len(controller.data_types),
            global_tag_count=len(controller.tags),
            program_count=len(controller.programs),
            program_tag_count=sum(len(program.tags) for program in controller.programs),
            raw=controller.raw,
        )
        for data_type in controller.data_types:
            data_type_fact = PlcDataTypeFact.objects.create(
                run=run,
                controller=controller_fact,
                name=data_type.name,
                description=data_type.description,
                is_aoi=data_type.is_aoi,
                member_count=len(data_type.members),
                raw=data_type.raw,
            )
            PlcMemberFact.objects.bulk_create(
                [
                    PlcMemberFact(
                        run=run,
                        data_type=data_type_fact,
                        name=member.name,
                        data_type_name=member.data_type,
                        array_dimensions=list(member.array_dimensions),
                        hidden=member.hidden,
                        description=member.description,
                        target=member.target,
                        bit_number=member.bit_number,
                        external_access=member.external_access,
                        usage=member.usage,
                        required=member.required,
                        visible=member.visible,
                        constant=member.constant,
                        radix=member.radix,
                        raw=member.raw,
                    )
                    for member in data_type.members
                ]
            )
        PlcTagFact.objects.bulk_create(
            [
                PlcTagFact(
                    run=run,
                    controller=controller_fact,
                    scope=tag.scope,
                    name=tag.name,
                    data_type_name=tag.data_type,
                    tag_type=tag.tag_type,
                    array_dimensions=list(tag.array_dimensions),
                    alias_for=tag.alias_for,
                    hidden=tag.hidden,
                    description=tag.description,
                    external_access=tag.external_access,
                    constant=tag.constant,
                    radix=tag.radix,
                    raw=tag.raw,
                )
                for tag in controller.all_tags()
            ]
        )
    return run


@transaction.atomic
def persist_factorytalk_project(run: MineRun, project: FactoryTalkProject) -> MineRun:
    run.source_sha256 = project.source_sha256
    run.summary = project.summary()
    run.status = MineRun.Status.COMPLETE
    run.completed_at = timezone.now()
    run.save(update_fields=["source_sha256", "summary", "status", "completed_at", "updated_at"])

    for screen in project.screens:
        screen_fact = HmiScreenFact.objects.create(
            run=run,
            name=screen.name,
            screen_type=screen.screen_type,
            source_path=screen.source_path,
            width=screen.width,
            height=screen.height,
            component_count=len(screen.components),
            tag_reference_count=len(screen.tag_references),
            raw={"source_path": screen.source_path},
        )
        for component in screen.components:
            component_fact = HmiComponentFact.objects.create(
                run=run,
                screen=screen_fact,
                name=component.name,
                component_type=component.component_type,
                bounds=component.bounds,
                global_object_reference=component.global_object_reference,
                raw=component.raw,
            )
            HmiTagReferenceFact.objects.bulk_create(
                [
                    HmiTagReferenceFact(
                        run=run,
                        screen=screen_fact,
                        component=component_fact,
                        original=reference.original,
                        shortcut=reference.shortcut,
                        scope=reference.scope,
                        base_tag=reference.base_tag,
                        member_path=reference.member_path,
                        raw_tag_path=reference.raw_tag_path,
                    )
                    for reference in component.tag_references
                ]
            )
    for parameter_file in project.parameter_files:
        parameter_file_fact = HmiParameterFileFact.objects.create(
            run=run,
            name=parameter_file.name,
            source_path=parameter_file.source_path,
            parameter_count=len(parameter_file.parameters),
        )
        HmiParameterFact.objects.bulk_create(
            [
                HmiParameterFact(run=run, parameter_file=parameter_file_fact, name=name, value=value)
                for name, value in sorted(parameter_file.parameters.items())
            ]
        )
    return run
