from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from flux_mine.hmi.factorytalk import FactoryTalkProject
from flux_mine.hmi.tag_refs import extract_hmi_tag_references
from flux_mine.imports import MineImport, parse_import_bytes, parse_import_path
from flux_mine.plc.models import PlcProject, PlcRung

from .models import (
    HmiComponentActionFact,
    HmiComponentFact,
    HmiComponentParameterFact,
    HmiComponentStateFact,
    HmiGlobalObjectLinkFact,
    HmiParameterFact,
    HmiParameterFileFact,
    HmiScreenFact,
    HmiTagReferenceFact,
    HmiVbaLinkFact,
    MineRun,
    PlcControllerFact,
    PlcDataTypeFact,
    PlcInstructionFact,
    PlcMemberFact,
    PlcProgramFact,
    PlcRoutineFact,
    PlcRungFact,
    PlcScheduledProgramFact,
    PlcTagFact,
    PlcTagReferenceFact,
    PlcTaskFact,
)


def mine_source(path: str | Path, *, source_type: str = "auto", label: str = "") -> MineRun:
    result = parse_import_path(path, source_type=source_type)
    return persist_mine_import(result, label=label)


def mine_uploaded_source(upload, *, source_type: str = "auto", label: str = "") -> MineRun:
    result = parse_import_bytes(upload.name, upload.read(), source_type=source_type)
    return persist_mine_import(result, label=label)


def mine_factorytalk_sqlite_export(
    path: str | Path,
    *,
    label: str = "",
    max_display_screens: int | None = 8,
) -> MineRun:
    """Persist the verified FactoryTalk recovery SQLite as Flux.mine facts."""
    sqlite_path = Path(path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"FactoryTalk recovery SQLite not found: {sqlite_path}")
    source_sha256 = hashlib.sha256(sqlite_path.read_bytes()).hexdigest()
    run = MineRun.objects.create(
        label=label or sqlite_path.name,
        source_type=MineRun.SourceType.FACTORYTALK,
        source_path=str(sqlite_path),
        source_sha256=source_sha256,
        status=MineRun.Status.RUNNING,
    )
    try:
        with sqlite3.connect(sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            persist_factorytalk_sqlite_export_run(
                run,
                connection,
                source_sha256=source_sha256,
                max_display_screens=max_display_screens,
            )
    except Exception as exc:
        run.status = MineRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


def persist_mine_import(result: MineImport, *, label: str = "") -> MineRun:
    run = MineRun.objects.create(
        label=label or Path(result.source_name).name,
        source_type=result.source_type,
        source_path=result.source_name,
        source_sha256=result.source_sha256,
        status=MineRun.Status.RUNNING,
    )
    try:
        if isinstance(result.project, PlcProject):
            persist_plc_project(run, result.project, import_summary=result.import_summary)
        elif isinstance(result.project, FactoryTalkProject):
            persist_factorytalk_project(run, result.project, import_summary=result.import_summary)
        else:
            raise ValueError(f"Unsupported mine import project: {type(result.project).__name__}")
    except Exception as exc:
        run.status = MineRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "error", "completed_at", "updated_at"])
        raise
    return run


@transaction.atomic
def persist_plc_project(
    run: MineRun, project: PlcProject, *, import_summary: dict | None = None
) -> MineRun:
    run.source_sha256 = project.source_sha256
    run.summary = summary_with_import(project.summary(), import_summary)
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
        program_facts: dict[str, PlcProgramFact] = {}
        rung_facts: list[tuple[str, PlcRungFact, PlcRung]] = []
        for program in controller.programs:
            program_fact = PlcProgramFact.objects.create(
                run=run,
                controller=controller_fact,
                name=program.name,
                main_routine_name=program.main_routine_name,
                raw=program.raw,
            )
            program_facts[program.name] = program_fact
            for routine in program.routines:
                routine_fact = PlcRoutineFact.objects.create(
                    run=run,
                    program=program_fact,
                    name=routine.name,
                    routine_type=routine.routine_type,
                    raw=routine.raw,
                )
                rung_rows = [
                    PlcRungFact(
                        run=run,
                        routine=routine_fact,
                        number=rung.number,
                        sort_order=sort_order,
                        rung_type=rung.rung_type,
                        text=rung.text,
                        comment=rung.comment,
                        raw=rung.raw,
                    )
                    for sort_order, rung in enumerate(routine.rungs)
                ]
                created_rungs = PlcRungFact.objects.bulk_create(rung_rows)
                rung_facts.extend(
                    (program.name, rung_fact, rung)
                    for rung_fact, rung in zip(created_rungs, routine.rungs, strict=True)
                )
        for task in controller.tasks:
            task_fact = PlcTaskFact.objects.create(
                run=run,
                controller=controller_fact,
                name=task.name,
                task_type=task.task_type,
                priority=task.priority,
                rate=task.rate,
                watchdog=task.watchdog,
                disable_update_outputs=task.disable_update_outputs,
                inhibit_task=task.inhibit_task,
                raw=task.raw,
            )
            PlcScheduledProgramFact.objects.bulk_create(
                [
                    PlcScheduledProgramFact(
                        run=run,
                        task=task_fact,
                        program=program_facts.get(program_name),
                        name=program_name,
                        sort_order=sort_order,
                    )
                    for sort_order, program_name in enumerate(task.scheduled_programs)
                ]
            )
        tag_rows = [
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
        PlcTagFact.objects.bulk_create(tag_rows)
        tag_facts = {
            (tag.scope, tag.name.lower()): tag
            for tag in PlcTagFact.objects.filter(controller=controller_fact)
        }
        persist_plc_instructions(run, rung_facts, tag_facts)
    return run


def persist_plc_instructions(
    run: MineRun,
    rung_facts: list[tuple[str, PlcRungFact, PlcRung]],
    tag_facts: dict[tuple[str, str], PlcTagFact],
) -> None:
    tag_reference_rows: list[PlcTagReferenceFact] = []
    for program_scope, rung_fact, rung in rung_facts:
        instruction_rows = [
            PlcInstructionFact(
                run=run,
                rung=rung_fact,
                sort_order=sort_order,
                mnemonic=instruction.mnemonic,
                operands=list(instruction.operands),
                raw=instruction.raw,
            )
            for sort_order, instruction in enumerate(rung.instructions)
        ]
        instruction_facts = PlcInstructionFact.objects.bulk_create(instruction_rows)
        for instruction_fact, instruction in zip(instruction_facts, rung.instructions, strict=True):
            for reference in instruction.tag_references:
                tag_fact = tag_facts.get((program_scope, reference.base_tag.lower())) or tag_facts.get(
                    ("Global", reference.base_tag.lower())
                )
                tag_reference_rows.append(
                    PlcTagReferenceFact(
                        run=run,
                        rung=rung_fact,
                        instruction=instruction_fact,
                        tag=tag_fact,
                        scope=tag_fact.scope if tag_fact is not None else program_scope,
                        original=reference.original,
                        base_tag=reference.base_tag,
                        member_path=reference.member_path,
                        operand_index=reference.operand_index,
                        role=reference.role,
                        raw=reference.raw,
                    )
                )
    PlcTagReferenceFact.objects.bulk_create(tag_reference_rows)


@transaction.atomic
def persist_factorytalk_project(
    run: MineRun,
    project: FactoryTalkProject,
    *,
    import_summary: dict | None = None,
) -> MineRun:
    run.source_sha256 = project.source_sha256
    run.summary = summary_with_import(project.summary(), import_summary)
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
        component_by_path: dict[str, HmiComponentFact] = {}
        for component in screen.components:
            component_fact = HmiComponentFact.objects.create(
                run=run,
                screen=screen_fact,
                parent_component=component_by_path.get(component.parent_path),
                name=component.name,
                component_type=component.component_type,
                component_path=component.component_path,
                parent_path=component.parent_path,
                depth=component.depth,
                sibling_index=component.sibling_index,
                children_count=component.children_count,
                is_group=component.is_group,
                is_global_instance=component.is_global_instance,
                bounds=component.bounds,
                geometry=component.geometry,
                global_object_reference=component.global_object_reference,
                raw=component.raw,
            )
            component_by_path[component.component_path] = component_fact
            create_hmi_tag_reference_facts(
                run,
                screen_fact,
                component_fact,
                component.tag_references,
                source_kind="component",
                source_path=component.component_path,
            )
            HmiComponentActionFact.objects.bulk_create(
                [
                    HmiComponentActionFact(
                        run=run,
                        screen=screen_fact,
                        component=component_fact,
                        name=action.name,
                        action_type=action.action_type,
                        value=action.value,
                        raw=action.raw,
                    )
                    for action in component.actions
                ]
            )
            for action in component.actions:
                create_hmi_tag_reference_facts(
                    run,
                    screen_fact,
                    component_fact,
                    action.tag_references,
                    source_kind="action",
                    source_path=f"{component.component_path}/action/{action.name}",
                    raw={"action": action.name, "action_type": action.action_type},
                )
            HmiComponentStateFact.objects.bulk_create(
                [
                    HmiComponentStateFact(
                        run=run,
                        screen=screen_fact,
                        component=component_fact,
                        state_id=state.state_id,
                        value=state.value,
                        caption=state.caption,
                        back_color=state.back_color,
                        border_color=state.border_color,
                        border_width=state.border_width,
                        font_size=state.font_size,
                        font_family=state.font_family,
                        text_color=state.text_color,
                        raw=state.raw,
                    )
                    for state in component.states
                ]
            )
            for state in component.states:
                create_hmi_tag_reference_facts(
                    run,
                    screen_fact,
                    component_fact,
                    state.tag_references,
                    source_kind="state",
                    source_path=f"{component.component_path}/state/{state.state_id}",
                    raw={"state_id": state.state_id, "value": state.value},
                )
            HmiComponentParameterFact.objects.bulk_create(
                [
                    HmiComponentParameterFact(
                        run=run,
                        screen=screen_fact,
                        component=component_fact,
                        name=parameter.name,
                        value=parameter.value,
                        description=parameter.description,
                        raw=parameter.raw,
                    )
                    for parameter in component.parameters
                ]
            )
            for parameter in component.parameters:
                create_hmi_tag_reference_facts(
                    run,
                    screen_fact,
                    component_fact,
                    parameter.tag_references,
                    source_kind="parameter",
                    source_path=f"{component.component_path}/parameter/{parameter.name}",
                    raw={"parameter": parameter.name},
                )
            if component.global_object_link is not None:
                link = component.global_object_link
                HmiGlobalObjectLinkFact.objects.create(
                    run=run,
                    screen=screen_fact,
                    component=component_fact,
                    reference=link.reference,
                    link_file=link.link_file,
                    link_object=link.link_object,
                    link_base_object=link.link_base_object,
                    link_size=link.link_size,
                    link_connections=link.link_connections,
                    link_animations=link.link_animations,
                    link_tooltip_text=link.link_tooltip_text,
                    raw=link.raw,
                )
            HmiVbaLinkFact.objects.bulk_create(
                [
                    HmiVbaLinkFact(
                        run=run,
                        screen=screen_fact,
                        component=component_fact,
                        name=vba_link.name,
                        value=vba_link.value,
                        raw=vba_link.raw,
                    )
                    for vba_link in component.vba_links
                ]
            )
            for vba_link in component.vba_links:
                create_hmi_tag_reference_facts(
                    run,
                    screen_fact,
                    component_fact,
                    vba_link.tag_references,
                    source_kind="vba",
                    source_path=f"{component.component_path}/vba/{vba_link.name}",
                    raw={"vba": vba_link.name},
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
                HmiParameterFact(
                    run=run, parameter_file=parameter_file_fact, name=name, value=value
                )
                for name, value in sorted(parameter_file.parameters.items())
            ]
        )
    return run


@transaction.atomic
def persist_factorytalk_sqlite_export_run(
    run: MineRun,
    connection: sqlite3.Connection,
    *,
    source_sha256: str,
    max_display_screens: int | None,
) -> MineRun:
    table_counts = sqlite_table_counts(connection)
    screen_rows = sqlite_selected_screen_rows(connection, max_display_screens=max_display_screens)
    run.source_sha256 = source_sha256
    run.summary = {
        "source": "factorytalk_recovery_sqlite",
        "screen_count": len(screen_rows),
        "component_count": 0,
        "tag_reference_count": 0,
        "sqlite_counts": table_counts,
        "import_limit": {"max_display_screens": max_display_screens},
    }
    run.status = MineRun.Status.COMPLETE
    run.completed_at = timezone.now()
    run.save(update_fields=["source_sha256", "summary", "status", "completed_at", "updated_at"])

    imported_components = 0
    imported_references = 0
    seen_screen_paths: set[str] = set()
    for screen_row in screen_rows:
        component_rows = sqlite_component_rows(connection, screen_row["id"])
        screen_source_path = unique_sqlite_screen_source_path(screen_row, seen_screen_paths)
        screen_fact = HmiScreenFact.objects.create(
            run=run,
            name=screen_row["name"],
            screen_type=screen_row["type"],
            source_path=screen_source_path,
            width=screen_row["width"],
            height=screen_row["height"],
            component_count=len(component_rows),
            tag_reference_count=0,
            raw={"sqlite_id": screen_row["id"]},
        )
        component_by_sqlite_id: dict[int, HmiComponentFact] = {}
        reference_count = 0
        for sibling_index, component_row in enumerate(component_rows):
            component_id = component_row["id"]
            parent_fact = component_by_sqlite_id.get(component_row["parent_id"])
            attrs = sqlite_component_attributes(connection, component_id)
            geometry = sqlite_component_geometry(connection, component_id)
            component_name = component_row["name"] or f"{component_row['type']}_{component_id}"
            component_path = sqlite_component_path(
                screen_fact.name, component_by_sqlite_id, component_row
            )
            component_fact = HmiComponentFact.objects.create(
                run=run,
                screen=screen_fact,
                parent_component=parent_fact,
                name=component_name,
                component_type=component_row["type"],
                component_path=component_path,
                parent_path=parent_fact.component_path if parent_fact else "",
                depth=component_path.count("/"),
                sibling_index=sibling_index,
                is_group=component_row["type"] == "group",
                is_global_instance=bool(component_row["is_global_instance"]),
                bounds={
                    "left": component_row["left"],
                    "top": component_row["top"],
                    "width": component_row["width"],
                    "height": component_row["height"],
                },
                geometry=geometry,
                global_object_reference=component_row["global_object_reference"] or "",
                raw={"sqlite_id": component_id, "attributes": attrs},
            )
            component_by_sqlite_id[component_id] = component_fact
            reference_count += create_hmi_tag_reference_facts_from_text(
                run,
                screen_fact,
                component_fact,
                "\n".join(str(value) for value in flattened_attribute_values(attrs)),
                source_kind="component",
                source_path=component_fact.component_path,
                raw={"source": "sqlite_attributes"},
            )
            reference_count += persist_sqlite_component_children(
                connection,
                run,
                screen_fact,
                component_fact,
                component_id,
            )
        imported_components += len(component_rows)
        imported_references += reference_count
        screen_fact.component_count = len(component_rows)
        screen_fact.tag_reference_count = reference_count
        screen_fact.save(update_fields=["component_count", "tag_reference_count"])

    run.summary = {
        **run.summary,
        "component_count": imported_components,
        "tag_reference_count": imported_references,
    }
    run.save(update_fields=["summary", "updated_at"])
    return run


def sqlite_table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for table in (
        "screens",
        "components",
        "attributes",
        "actions",
        "states",
        "global_links",
        "parameters",
        "component_geometry",
    ):
        counts[table] = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return counts


def sqlite_selected_screen_rows(
    connection: sqlite3.Connection,
    *,
    max_display_screens: int | None,
) -> list[sqlite3.Row]:
    if max_display_screens is None:
        return list(connection.execute("SELECT * FROM screens ORDER BY id"))
    return list(
        connection.execute(
            "SELECT * FROM screens WHERE type = 'display' ORDER BY id LIMIT ?",
            (max_display_screens,),
        )
    )


def sqlite_component_rows(connection: sqlite3.Connection, screen_id: int) -> list[sqlite3.Row]:
    return list(
        connection.execute("SELECT * FROM components WHERE screen_id = ? ORDER BY id", (screen_id,))
    )


def unique_sqlite_screen_source_path(screen_row: sqlite3.Row, seen_paths: set[str]) -> str:
    base_path = (
        screen_row["original_path"] or screen_row["name"] or f"sqlite-screen-{screen_row['id']}"
    )
    if base_path not in seen_paths:
        seen_paths.add(base_path)
        return base_path
    deduped_path = f"{base_path}#sqlite-{screen_row['id']}"
    seen_paths.add(deduped_path)
    return deduped_path


def sqlite_component_attributes(connection: sqlite3.Connection, component_id: int) -> dict:
    attrs: dict[str, str | list[str]] = {}
    for row in connection.execute(
        "SELECT key, value FROM attributes WHERE component_id = ? ORDER BY id",
        (component_id,),
    ):
        key = row["key"]
        value = row["value"] or ""
        if key not in attrs:
            attrs[key] = value
        elif isinstance(attrs[key], list):
            attrs[key].append(value)
        else:
            attrs[key] = [attrs[key], value]
    return attrs


def sqlite_component_geometry(connection: sqlite3.Connection, component_id: int) -> dict:
    geometry: dict[str, list] = {}
    for row in connection.execute(
        "SELECT geometry_type, geometry_json FROM component_geometry WHERE component_id = ? ORDER BY id",
        (component_id,),
    ):
        try:
            value = json.loads(row["geometry_json"])
        except json.JSONDecodeError:
            value = row["geometry_json"]
        geometry.setdefault(row["geometry_type"], []).append(value)
    return geometry


def sqlite_component_path(
    screen_name: str,
    component_by_sqlite_id: dict[int, HmiComponentFact],
    component_row: sqlite3.Row,
) -> str:
    component_name = component_row["name"] or component_row["type"]
    local = f"{component_name}#{component_row['id']}"
    parent = component_by_sqlite_id.get(component_row["parent_id"])
    if parent:
        return f"{parent.component_path}/{local}"
    return f"{screen_name}/{local}"


def flattened_attribute_values(attrs: dict) -> list[str]:
    values: list[str] = []
    for value in attrs.values():
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        else:
            values.append(str(value))
    return values


def persist_sqlite_component_children(
    connection: sqlite3.Connection,
    run: MineRun,
    screen_fact: HmiScreenFact,
    component_fact: HmiComponentFact,
    component_id: int,
) -> int:
    reference_count = 0
    action_rows = list(
        connection.execute(
            "SELECT * FROM actions WHERE component_id = ? ORDER BY id", (component_id,)
        )
    )
    HmiComponentActionFact.objects.bulk_create(
        [
            HmiComponentActionFact(
                run=run,
                screen=screen_fact,
                component=component_fact,
                name=row["action_type"],
                action_type=row["action_type"],
                value=row["ftv_script"] or row["ignition_script"] or "",
                raw={
                    "sqlite_id": row["id"],
                    "ftv_script": row["ftv_script"],
                    "ignition_script": row["ignition_script"],
                },
            )
            for row in action_rows
        ]
    )
    for row in action_rows:
        reference_count += create_hmi_tag_reference_facts_from_text(
            run,
            screen_fact,
            component_fact,
            "\n".join(value or "" for value in (row["ftv_script"], row["ignition_script"])),
            source_kind="action",
            source_path=f"{component_fact.component_path}/action/{row['id']}",
            raw={"sqlite_id": row["id"], "action_type": row["action_type"]},
        )
    state_rows = list(
        connection.execute(
            "SELECT * FROM states WHERE component_id = ? ORDER BY id", (component_id,)
        )
    )
    HmiComponentStateFact.objects.bulk_create(
        [
            HmiComponentStateFact(
                run=run,
                screen=screen_fact,
                component=component_fact,
                state_id=row["stateId"] or "",
                value=row["value"] or "",
                caption=row["caption"] or "",
                back_color=row["backColor"] or "",
                border_color=row["borderColor"] or "",
                border_width=row["borderWidth"] or "",
                font_size=row["fontSize"] or "",
                font_family=row["fontFamily"] or "",
                text_color=row["textColor"] or "",
                raw={"sqlite_id": row["id"]},
            )
            for row in state_rows
        ]
    )
    for row in state_rows:
        reference_count += create_hmi_tag_reference_facts_from_text(
            run,
            screen_fact,
            component_fact,
            "\n".join(str(row[key] or "") for key in row.keys()),
            source_kind="state",
            source_path=f"{component_fact.component_path}/state/{row['id']}",
            raw={"sqlite_id": row["id"]},
        )
    parameter_rows = list(
        connection.execute(
            "SELECT * FROM parameters WHERE component_id = ? ORDER BY id", (component_id,)
        )
    )
    HmiComponentParameterFact.objects.bulk_create(
        [
            HmiComponentParameterFact(
                run=run,
                screen=screen_fact,
                component=component_fact,
                name=row["name"],
                value=row["value"] or "",
                description=row["description"] or "",
                raw={"sqlite_id": row["id"]},
            )
            for row in parameter_rows
        ]
    )
    for row in parameter_rows:
        reference_count += create_hmi_tag_reference_facts_from_text(
            run,
            screen_fact,
            component_fact,
            "\n".join(value or "" for value in (row["value"], row["description"])),
            source_kind="parameter",
            source_path=f"{component_fact.component_path}/parameter/{row['id']}",
            raw={"sqlite_id": row["id"], "parameter": row["name"]},
        )
    link_rows = list(
        connection.execute(
            "SELECT * FROM global_links WHERE component_id = ? ORDER BY id", (component_id,)
        )
    )
    HmiGlobalObjectLinkFact.objects.bulk_create(
        [
            HmiGlobalObjectLinkFact(
                run=run,
                screen=screen_fact,
                component=component_fact,
                reference=row["linkBaseObject"] or component_fact.global_object_reference,
                link_base_object=row["linkBaseObject"] or "",
                link_size=row["linkSize"] or "",
                link_connections=row["linkConnections"] or "",
                link_animations=row["linkAnimations"] or "",
                link_tooltip_text=row["linkToolTipText"] or "",
                raw={"sqlite_id": row["id"]},
            )
            for row in link_rows
        ]
    )
    return reference_count


def create_hmi_tag_reference_facts_from_text(
    run: MineRun,
    screen_fact: HmiScreenFact,
    component_fact: HmiComponentFact,
    text: str,
    *,
    source_kind: str,
    source_path: str,
    raw: dict | None = None,
) -> int:
    references = extract_hmi_tag_references(text)
    create_hmi_tag_reference_facts(
        run,
        screen_fact,
        component_fact,
        references,
        source_kind=source_kind,
        source_path=source_path,
        raw=raw,
    )
    return len(references)


def create_hmi_tag_reference_facts(
    run: MineRun,
    screen_fact: HmiScreenFact,
    component_fact: HmiComponentFact,
    references,
    *,
    source_kind: str,
    source_path: str,
    raw: dict | None = None,
) -> None:
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
                source_kind=source_kind,
                source_path=source_path,
                raw=raw or {},
            )
            for reference in references
        ]
    )


def summary_with_import(summary: dict, import_summary: dict | None) -> dict:
    if not import_summary:
        return summary
    return {**summary, "import": import_summary}
