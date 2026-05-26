from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Any

from django.db import transaction
from django.utils.text import slugify

from flux.mine.models import HmiComponentFact, MineRun

from .models import (
    Bundle,
    Cell,
    Comment,
    Point,
    Relationship,
    Source,
    Visual,
)


@dataclass(frozen=True)
class CellBundleImportResult:
    bundles: int
    cells: int
    points: int
    relationships: int = 0
    visuals: int = 0
    sources: int = 0


@dataclass(frozen=True)
class CellDraftBuildResult:
    bundle: Bundle
    cell: Cell
    sources: int
    points: int


@dataclass(frozen=True)
class CellDemoSeedResult:
    bundle: Bundle
    cells: int
    points: int
    runtime_tags: int
    plane_sample_points: int
    anchor_url: str


@transaction.atomic
def seed_demo_cell_bundle(*, include_runtime: bool = True) -> CellDemoSeedResult:
    bundle, _ = Bundle.objects.update_or_create(
        key="demo-pad",
        defaults={
            "name": "Demo Pad",
            "description": "Seeded Flux.cell sample with cached runtime and trace values.",
            "source_name": "flux.cell demo seed",
            "source_sha256": "",
            "enabled": True,
        },
    )
    pump, _ = Cell.objects.update_or_create(
        bundle=bundle,
        slug="pump-101",
        defaults={
            "name": "Pump 101",
            "group": "Demo Area",
            "kind": "Pump",
            "description": "Sample pump cell backed by cached runtime values.",
            "sort_order": 1,
            "enabled": True,
        },
    )
    tank, _ = Cell.objects.update_or_create(
        bundle=bundle,
        slug="tank-101",
        defaults={
            "name": "Tank 101",
            "group": "Demo Area",
            "kind": "Tank",
            "description": "Sample downstream tank cell.",
            "sort_order": 2,
            "enabled": True,
        },
    )

    for from_cell, relationship, to_cell, label, sort_order in (
        (pump, "next_area", tank, "Next Area", 1),
        (tank, "prev_area", pump, "Previous Area", 1),
        (tank, "child", pump, "Fed By", 2),
    ):
        Relationship.objects.update_or_create(
            from_cell=from_cell,
            relationship_type=relationship,
            to_cell=to_cell,
            defaults={
                "label": label,
                "sort_order": sort_order,
                "enabled": True,
                "raw": {"source": "demo_seed"},
            },
        )

    point_specs = (
        (
            pump,
            "pressure",
            "Pressure",
            "[default]Demo/Pump101/Pressure",
            "pv",
            "psi",
            True,
            True,
            1,
            1,
            "pressure",
            0.0,
            100.0,
            "#35a7ff",
        ),
        (
            pump,
            "running",
            "Running",
            "[default]Demo/Pump101/Running",
            "status",
            "",
            True,
            False,
            2,
            0,
            "",
            None,
            None,
            "#67e8f9",
        ),
        (
            pump,
            "speed",
            "Speed",
            "[default]Demo/Pump101/Speed",
            "pv",
            "Hz",
            True,
            True,
            3,
            2,
            "speed",
            0.0,
            60.0,
            "#fbbf24",
        ),
        (
            tank,
            "level",
            "Level",
            "[default]Demo/Tank101/Level",
            "pv",
            "%",
            True,
            True,
            1,
            1,
            "level",
            0.0,
            100.0,
            "#a78bfa",
        ),
    )
    for (
        cell,
        key,
        label,
        full_path,
        role,
        units,
        include_live,
        include_trace,
        live_order,
        trace_order,
        axis_key,
        range_min,
        range_max,
        color,
    ) in point_specs:
        Point.objects.update_or_create(
            cell=cell,
            key=key,
            defaults={
                "label": label,
                "full_path": full_path,
                "role": role,
                "engineering_units": units,
                "include_live": include_live,
                "include_trace": include_trace,
                "live_order": live_order,
                "trace_order": trace_order,
                "axis_key": axis_key,
                "range_min": range_min,
                "range_max": range_max,
                "color": color,
                "enabled": True,
            },
        )

    for cell, visual_type, source_key, symbol, x, y, width, height in (
        (pump, "sample_icon", "demo-pump", "P", 10.0, 20.0, 100.0, 80.0),
        (tank, "sample_icon", "demo-tank", "T", 150.0, 18.0, 110.0, 96.0),
    ):
        Visual.objects.update_or_create(
            cell=cell,
            visual_type=visual_type,
            source_item_key=source_key,
            defaults={
                "source_system": "seed",
                "source_screen_key": "demo",
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "sort_order": 1,
                "enabled": True,
                "raw": {"symbol": symbol},
            },
        )
        Source.objects.update_or_create(
            cell=cell,
            source_type="sample_seed",
            component_path=source_key,
            defaults={
                "screen_name": "Demo",
                "component_name": cell.name,
                "component_type": cell.kind,
                "bounds": {"left": x, "top": y, "width": width, "height": height},
                "raw": {"source": "demo_seed"},
            },
        )

    Comment.objects.get_or_create(
        cell=pump,
        body="Seeded sample cell: cached runtime values only.",
        defaults={"author_name": "Sam"},
    )

    runtime_tags = 0
    plane_sample_points = 0
    if include_runtime:
        runtime_tags, plane_sample_points = seed_demo_cell_runtime_cache()

    return CellDemoSeedResult(
        bundle=bundle,
        cells=2,
        points=len(point_specs),
        runtime_tags=runtime_tags,
        plane_sample_points=plane_sample_points,
        anchor_url="/cell/#cell-demo-pad-pump-101",
    )


def seed_demo_cell_runtime_cache() -> tuple[int, int]:
    from datetime import timedelta

    from django.utils import timezone

    from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample, TagSchedule
    from flux.plane.models import Sample
    from flux.plane.services import ensure_series_for_full_path
    from flux.trace.models import TraceProfile, TraceSignal

    schedule, _ = TagSchedule.objects.get_or_create(
        name="demo-cell-fast",
        defaults={"interval_seconds": 1, "enabled": True},
    )
    profile, _ = TraceProfile.objects.update_or_create(
        key="demo-pad-pump-101",
        defaults={"label": "Demo Pad Pump 101", "enabled": True, "cache_enabled": True},
    )
    now = timezone.now()
    tag_specs = (
        {
            "provider": "default",
            "path": "Demo/Pump101/Pressure",
            "display_name": "Pressure",
            "asset_name": "Demo Area: Pump 101",
            "units": "psi",
            "latest": 47.25,
            "samples": (43.25, 45.5, 47.25),
            "trace": (43.25, 45.5, 47.25),
            "sort_order": 1,
        },
        {
            "provider": "default",
            "path": "Demo/Pump101/Running",
            "display_name": "Running",
            "asset_name": "Demo Area: Pump 101",
            "units": "",
            "latest": True,
            "samples": (True,),
            "trace": (),
            "sort_order": 0,
        },
        {
            "provider": "default",
            "path": "Demo/Pump101/Speed",
            "display_name": "Speed",
            "asset_name": "Demo Area: Pump 101",
            "units": "Hz",
            "latest": 42.0,
            "samples": (38.0, 40.0, 42.0),
            "trace": (38.0, 40.0, 42.0),
            "sort_order": 2,
        },
        {
            "provider": "default",
            "path": "Demo/Tank101/Level",
            "display_name": "Level",
            "asset_name": "Demo Area: Tank 101",
            "units": "%",
            "latest": 73.4,
            "samples": (69.5, 71.2, 73.4),
            "trace": (69.5, 71.2, 73.4),
            "sort_order": 3,
        },
    )

    trace_point_count = 0
    for spec in tag_specs:
        tag, _ = RuntimeTag.objects.update_or_create(
            provider=spec["provider"],
            path=spec["path"],
            defaults={
                "display_name": spec["display_name"],
                "asset_name": spec["asset_name"],
                "engineering_units": spec["units"],
                "schedule": schedule,
                "enabled": True,
            },
        )
        LatestTagValue.objects.update_or_create(
            tag=tag,
            defaults={
                "value": spec["latest"],
                "quality_code": "Good",
                "value_timestamp": now,
                "read_at": now,
            },
        )
        TagSample.objects.filter(tag=tag).delete()
        for index, sample_value in enumerate(spec["samples"]):
            sample_time = now - timedelta(seconds=(len(spec["samples"]) - index) * 20)
            TagSample.objects.create(
                tag=tag,
                value=sample_value,
                quality_code="Good",
                value_timestamp=sample_time,
                read_at=sample_time,
            )
        if spec["trace"]:
            signal, _ = TraceSignal.objects.update_or_create(
                profile=profile,
                tag=tag,
                defaults={
                    "label": spec["display_name"],
                    "series": ensure_series_for_full_path(tag.full_path),
                    "unit": spec["units"],
                    "axis_key": spec["display_name"].lower(),
                    "sort_order": spec["sort_order"],
                    "cache_enabled": True,
                },
            )
            Sample.objects.filter(series_id=signal.series_id).delete()
            for index, sample_value in enumerate(spec["trace"]):
                trace_time = now - timedelta(seconds=(len(spec["trace"]) - index) * 30)
                Sample.objects.create(
                    series_id=signal.series_id,
                    timestamp=trace_time,
                    value_float=sample_value,
                    quality_code="Good",
                )
                trace_point_count += 1

    return len(tag_specs), trace_point_count


def import_cell_bundle_path(path: str | Path, *, replace: bool = False) -> CellBundleImportResult:
    bundle_path = Path(path)
    cells_path = bundle_path / "cells.csv"
    points_path = bundle_path / "points.csv"
    if not cells_path.exists() or not points_path.exists():
        raise ValueError("Cell CSV bundle requires cells.csv and points.csv")
    return import_cell_bundle_rows(
        read_csv_rows(cells_path),
        read_csv_rows(points_path),
        relationship_rows=read_optional_csv_rows(bundle_path / "relationships.csv"),
        visual_rows=read_optional_csv_rows(bundle_path / "visuals.csv"),
        source_rows=read_optional_csv_rows(bundle_path / "sources.csv"),
        replace=replace,
        source_name=str(bundle_path),
    )


def import_cell_bundle_zip_bytes(
    filename: str, content: bytes, *, replace: bool = False
) -> CellBundleImportResult:
    with TemporaryDirectory(prefix="flux-cell-csv-") as temp_dir:
        extract_root = Path(temp_dir)
        extract_cell_csv_zip(content, extract_root)
        bundle_dir = find_cell_bundle_dir(extract_root)
        return import_cell_bundle_rows(
            read_csv_rows(bundle_dir / "cells.csv"),
            read_csv_rows(bundle_dir / "points.csv"),
            relationship_rows=read_optional_csv_rows(bundle_dir / "relationships.csv"),
            visual_rows=read_optional_csv_rows(bundle_dir / "visuals.csv"),
            source_rows=read_optional_csv_rows(bundle_dir / "sources.csv"),
            replace=replace,
            source_name=filename,
        )


@transaction.atomic
def import_cell_bundle_rows(
    cell_rows: Iterable[dict[str, str]],
    point_rows: Iterable[dict[str, str]],
    *,
    relationship_rows: Iterable[dict[str, str]] | None = None,
    visual_rows: Iterable[dict[str, str]] | None = None,
    source_rows: Iterable[dict[str, str]] | None = None,
    replace: bool = False,
    source_name: str = "",
) -> CellBundleImportResult:
    bundles_seen: set[str] = set()
    cells_seen: set[tuple[str, str]] = set()
    points_seen: set[tuple[str, str, str]] = set()
    relationships_seen: set[tuple[str, str, str, str]] = set()
    visuals_seen = 0
    sources_seen = 0

    for row_number, row in enumerate(cell_rows, start=2):
        bundle_key = required(row, "bundle", row_number)
        cell_slug = required(row, "cell_slug", row_number)
        name = required(row, "name", row_number)
        kind = required(row, "kind", row_number)
        bundle, _ = Bundle.objects.update_or_create(
            key=bundle_key,
            defaults={
                "name": value_or(row, "bundle_name", bundle_key),
                "description": value_or(row, "bundle_description", ""),
                "source_name": source_name,
                "source_sha256": row_sha256(row),
                "enabled": parse_bool(value_or(row, "enabled", "true")),
            },
        )
        if replace and bundle_key not in bundles_seen:
            bundle.cells.all().delete()
        bundles_seen.add(bundle_key)
        Cell.objects.update_or_create(
            bundle=bundle,
            slug=cell_slug,
            defaults={
                "name": name,
                "group": value_or(row, "group", ""),
                "kind": kind,
                "description": value_or(row, "description", ""),
                "sort_order": parse_int(value_or(row, "sort_order", "0")),
                "enabled": parse_bool(value_or(row, "enabled", "true")),
            },
        )
        cells_seen.add((bundle_key, cell_slug))

    for row_number, row in enumerate(point_rows, start=2):
        bundle_key = required(row, "bundle", row_number)
        cell_slug = required(row, "cell_slug", row_number)
        point_key = required(row, "key", row_number)
        label = required(row, "label", row_number)
        full_path = required(row, "full_path", row_number)
        validate_tag_path(full_path, row_number)
        try:
            cell = Cell.objects.select_related("bundle").get(
                bundle__key=bundle_key, slug=cell_slug
            )
        except Cell.DoesNotExist as exc:
            raise ValueError(
                f"Row {row_number}: point references unknown cell {bundle_key}/{cell_slug}"
            ) from exc
        Point.objects.update_or_create(
            cell=cell,
            key=point_key,
            defaults={
                "label": label,
                "full_path": full_path,
                "role": value_or(row, "role", ""),
                "engineering_units": value_or(row, "engineering_units", ""),
                "include_live": parse_bool(value_or(row, "include_live", "true")),
                "include_trace": parse_bool(value_or(row, "include_trace", "false")),
                "live_order": parse_int(value_or(row, "live_order", "0")),
                "trace_order": parse_int(value_or(row, "trace_order", "0")),
                "axis_key": value_or(row, "axis_key", ""),
                "range_min": parse_float_or_none(value_or(row, "range_min", "")),
                "range_max": parse_float_or_none(value_or(row, "range_max", "")),
                "color": value_or(row, "color", ""),
                "enabled": parse_bool(value_or(row, "enabled", "true")),
            },
        )
        points_seen.add((bundle_key, cell_slug, point_key))

    for row_number, row in enumerate(relationship_rows or [], start=2):
        bundle_key = required(row, "bundle", row_number)
        from_slug = required(row, "from_cell_slug", row_number)
        to_slug = required(row, "to_cell_slug", row_number)
        relationship_type = required(row, "relationship", row_number)
        from_cell = get_cell(bundle_key, from_slug, row_number)
        to_cell = get_cell(bundle_key, to_slug, row_number)
        Relationship.objects.update_or_create(
            from_cell=from_cell,
            to_cell=to_cell,
            relationship_type=relationship_type,
            defaults={
                "label": value_or(row, "label", ""),
                "sort_order": parse_int(value_or(row, "sort_order", "0")),
                "enabled": parse_bool(value_or(row, "enabled", "true")),
                "raw": {"csv": row},
            },
        )
        relationships_seen.add((bundle_key, from_slug, relationship_type, to_slug))

    for row_number, row in enumerate(visual_rows or [], start=2):
        bundle_key = required(row, "bundle", row_number)
        cell_slug = required(row, "cell_slug", row_number)
        visual_type = required(row, "visual_type", row_number)
        cell = get_cell(bundle_key, cell_slug, row_number)
        Visual.objects.update_or_create(
            cell=cell,
            visual_type=visual_type,
            source_item_key=value_or(row, "source_item_key", ""),
            defaults={
                "source_system": value_or(row, "source_system", ""),
                "mine_run": mine_run_or_none(value_or(row, "source_run_id", "")),
                "source_screen_key": value_or(row, "source_screen_key", ""),
                "x": parse_float_or_none(value_or(row, "x", "")),
                "y": parse_float_or_none(value_or(row, "y", "")),
                "width": parse_float_or_none(value_or(row, "width", "")),
                "height": parse_float_or_none(value_or(row, "height", "")),
                "sort_order": parse_int(value_or(row, "sort_order", "0")),
                "enabled": parse_bool(value_or(row, "enabled", "true")),
                "raw": {"csv": row},
            },
        )
        visuals_seen += 1

    for row_number, row in enumerate(source_rows or [], start=2):
        bundle_key = required(row, "bundle", row_number)
        cell_slug = required(row, "cell_slug", row_number)
        source_type = required(row, "source_type", row_number)
        component_path = value_or(row, "source_component_key", "") or value_or(
            row, "component_path", ""
        )
        cell = get_cell(bundle_key, cell_slug, row_number)
        Source.objects.update_or_create(
            cell=cell,
            source_type=source_type,
            component_path=component_path,
            defaults={
                "mine_run": mine_run_or_none(value_or(row, "source_run_id", "")),
                "screen_name": value_or(row, "screen_name", value_or(row, "source_screen_key", "")),
                "component_name": value_or(row, "component_name", ""),
                "component_type": value_or(row, "component_type", ""),
                "bounds": parse_json_object(value_or(row, "bounds_json", "")),
                "raw": parse_json_object(value_or(row, "raw_json", "")) or {"csv": row},
            },
        )
        sources_seen += 1

    return CellBundleImportResult(
        bundles=len(bundles_seen),
        cells=len(cells_seen),
        points=len(points_seen),
        relationships=len(relationships_seen),
        visuals=visuals_seen,
        sources=sources_seen,
    )


def live_scope_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    rows: list[dict[str, Any]] = []
    for cell in bundle.cells.filter(enabled=True).prefetch_related("points"):
        for point in cell.points.filter(enabled=True, include_live=True).order_by(
            "live_order", "label"
        ):
            rows.append(
                {
                    "scope": bundle.key,
                    "scope_name": bundle.name,
                    "description": bundle.description,
                    "card": cell.name,
                    "group": cell.group,
                    "kind": cell.kind,
                    "card_order": cell.sort_order,
                    "point": point.label,
                    "full_path": point.full_path,
                    "point_order": point.live_order,
                }
            )
    return rows


def trace_scope_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    rows: list[dict[str, Any]] = []
    for cell in bundle.cells.filter(enabled=True).prefetch_related("points"):
        points = list(
            cell.points.filter(enabled=True, include_trace=True).order_by(
                "trace_order", "live_order", "label"
            )
        )
        if not points:
            continue
        row: dict[str, Any] = {
            "Chart Scope": f"{bundle.key}-{cell.slug}",
            "ID": cell.slug,
            "Name": cell.name,
            "display order": cell.sort_order,
        }
        for index, point in enumerate(points, start=1):
            row[f"Tag {index}"] = point.full_path
        rows.append(row)
    return rows


def write_cell_bundle_exports(bundle_key: str, output_dir: str | Path) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    cells_path = target / "cells.csv"
    points_path = target / "points.csv"
    relationships_path = target / "relationships.csv"
    visuals_path = target / "visuals.csv"
    sources_path = target / "sources.csv"
    live_path = target / "live_scope.csv"
    trace_path = target / "trace_scopes.csv"
    write_csv(cells_path, cell_rows(bundle_key), CELL_HEADERS)
    write_csv(points_path, point_rows(bundle_key), POINT_HEADERS)
    write_csv(relationships_path, relationship_rows(bundle_key), RELATIONSHIP_HEADERS)
    write_csv(visuals_path, visual_rows(bundle_key), VISUAL_HEADERS)
    write_csv(sources_path, source_rows(bundle_key), SOURCE_HEADERS)
    write_csv(live_path, live_scope_rows(bundle_key), LIVE_HEADERS)
    trace_rows = trace_scope_rows(bundle_key)
    trace_headers = trace_headers_for_rows(trace_rows)
    write_csv(trace_path, trace_rows, trace_headers)
    return {
        "cells": cells_path,
        "points": points_path,
        "relationships": relationships_path,
        "visuals": visuals_path,
        "sources": sources_path,
        "live_scope": live_path,
        "trace_scopes": trace_path,
    }


def cell_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    return [
        {
            "bundle": bundle.key,
            "bundle_name": bundle.name,
            "cell_slug": cell.slug,
            "name": cell.name,
            "group": cell.group,
            "kind": cell.kind,
            "description": cell.description,
            "sort_order": cell.sort_order,
            "enabled": cell.enabled,
        }
        for cell in bundle.cells.all()
    ]


def point_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    rows: list[dict[str, Any]] = []
    for cell in bundle.cells.prefetch_related("points"):
        for point in cell.points.all():
            rows.append(
                {
                    "bundle": bundle.key,
                    "cell_slug": cell.slug,
                    "key": point.key,
                    "label": point.label,
                    "full_path": point.full_path,
                    "role": point.role,
                    "engineering_units": point.engineering_units,
                    "include_live": point.include_live,
                    "include_trace": point.include_trace,
                    "live_order": point.live_order,
                    "trace_order": point.trace_order,
                    "axis_key": point.axis_key,
                    "range_min": point.range_min if point.range_min is not None else "",
                    "range_max": point.range_max if point.range_max is not None else "",
                    "color": point.color,
                    "enabled": point.enabled,
                }
            )
    return rows


def relationship_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    rows: list[dict[str, Any]] = []
    for relationship in Relationship.objects.filter(
        from_cell__bundle=bundle
    ).select_related("from_cell", "to_cell"):
        rows.append(
            {
                "bundle": bundle.key,
                "from_cell_slug": relationship.from_cell.slug,
                "relationship": relationship.relationship_type,
                "to_cell_slug": relationship.to_cell.slug,
                "label": relationship.label,
                "sort_order": relationship.sort_order,
                "enabled": relationship.enabled,
            }
        )
    return rows


def visual_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    rows: list[dict[str, Any]] = []
    for visual in Visual.objects.filter(cell__bundle=bundle).select_related(
        "cell", "mine_run"
    ):
        rows.append(
            {
                "bundle": bundle.key,
                "cell_slug": visual.cell.slug,
                "visual_type": visual.visual_type,
                "source_system": visual.source_system,
                "source_run_id": visual.mine_run_id or "",
                "source_screen_key": visual.source_screen_key,
                "source_item_key": visual.source_item_key,
                "x": visual.x if visual.x is not None else "",
                "y": visual.y if visual.y is not None else "",
                "width": visual.width if visual.width is not None else "",
                "height": visual.height if visual.height is not None else "",
                "sort_order": visual.sort_order,
                "enabled": visual.enabled,
            }
        )
    return rows


def source_rows(bundle_key: str) -> list[dict[str, Any]]:
    bundle = Bundle.objects.get(key=bundle_key)
    rows: list[dict[str, Any]] = []
    for source in Source.objects.filter(cell__bundle=bundle).select_related(
        "cell", "mine_run"
    ):
        rows.append(
            {
                "bundle": bundle.key,
                "cell_slug": source.cell.slug,
                "source_type": source.source_type,
                "source_run_id": source.mine_run_id or "",
                "source_screen_key": source.screen_name,
                "source_component_key": source.component_path,
                "screen_name": source.screen_name,
                "component_path": source.component_path,
                "component_name": source.component_name,
                "component_type": source.component_type,
                "bounds_json": json.dumps(source.bounds, sort_keys=True),
                "raw_json": json.dumps(source.raw, sort_keys=True),
            }
        )
    return rows


@transaction.atomic
def create_cell_draft_from_hmi_components(
    mine_run: MineRun,
    component_ids: list[int],
    *,
    bundle_key: str,
    bundle_name: str,
    cell_slug: str,
    cell_name: str,
    group: str = "",
    kind: str = "Recovered",
    replace: bool = True,
) -> CellDraftBuildResult:
    if not component_ids:
        raise ValueError("Select at least one HMI component before creating a cell draft")
    normalized_bundle_key = safe_slug(bundle_key, "hmi-draft")
    normalized_cell_slug = safe_slug(cell_slug, "cell-draft")
    bundle, _ = Bundle.objects.update_or_create(
        key=normalized_bundle_key,
        defaults={
            "name": bundle_name or normalized_bundle_key,
            "description": "Draft cells created from selected HMI map components.",
            "source_name": mine_run.source_path,
            "source_sha256": mine_run.source_sha256,
            "enabled": True,
        },
    )
    cell, _ = Cell.objects.update_or_create(
        bundle=bundle,
        slug=normalized_cell_slug,
        defaults={
            "name": cell_name or normalized_cell_slug,
            "group": group,
            "kind": kind or "Recovered",
            "description": f"Draft from HMI mine run {mine_run.id}",
            "enabled": True,
        },
    )
    if replace:
        cell.points.all().delete()
        cell.sources.all().delete()
        cell.visuals.all().delete()

    components = list(
        HmiComponentFact.objects.filter(run=mine_run, id__in=component_ids)
        .select_related("screen")
        .prefetch_related("tag_references")
        .order_by("screen__name", "component_path", "id")
    )
    source_count = 0
    point_count = 0
    seen_paths: set[str] = set()
    for component in components:
        Source.objects.update_or_create(
            cell=cell,
            source_type="hmi_component",
            component_path=component.component_path or str(component.id),
            defaults={
                "mine_run": mine_run,
                "screen": component.screen,
                "component": component,
                "screen_name": component.screen.name,
                "component_name": component.name,
                "component_type": component.component_type,
                "bounds": component.bounds,
                "raw": {
                    "is_group": component.is_group,
                    "is_global_instance": component.is_global_instance,
                    "global_object_reference": component.global_object_reference,
                    "geometry": component.geometry,
                },
            },
        )
        Visual.objects.update_or_create(
            cell=cell,
            visual_type="symbolic_hmi_component",
            source_item_key=component.component_path or str(component.id),
            defaults={
                "source_system": "hmi",
                "mine_run": mine_run,
                "screen": component.screen,
                "component": component,
                "source_screen_key": component.screen.source_path or component.screen.name,
                "x": component.bounds.get("left"),
                "y": component.bounds.get("top"),
                "width": component.bounds.get("width"),
                "height": component.bounds.get("height"),
                "sort_order": source_count,
                "enabled": True,
                "raw": {
                    "component_type": component.component_type,
                    "component_name": component.name,
                },
            },
        )
        source_count += 1
        is_control = is_control_component(component.component_type)
        for reference in component.tag_references.all():
            full_path = normalized_tag_path(reference.original)
            if not full_path or full_path in seen_paths:
                continue
            seen_paths.add(full_path)
            is_source_action = reference.source_kind in {"action", "vba"}
            Point.objects.update_or_create(
                cell=cell,
                key=safe_slug(
                    f"{reference.base_tag}-{reference.member_path or reference.scope}",
                    f"point-{point_count + 1}",
                ),
                defaults={
                    "label": point_label(reference),
                    "full_path": full_path,
                    "role": reference.source_kind,
                    "include_live": not is_control and not is_source_action,
                    "include_trace": not is_control and not is_source_action,
                    "live_order": point_count + 1,
                    "trace_order": point_count + 1,
                    "enabled": True,
                },
            )
            point_count += 1
    return CellDraftBuildResult(bundle=bundle, cell=cell, sources=source_count, points=point_count)


CELL_HEADERS = [
    "bundle",
    "bundle_name",
    "cell_slug",
    "name",
    "group",
    "kind",
    "description",
    "sort_order",
    "enabled",
]
POINT_HEADERS = [
    "bundle",
    "cell_slug",
    "key",
    "label",
    "full_path",
    "role",
    "engineering_units",
    "include_live",
    "include_trace",
    "live_order",
    "trace_order",
    "axis_key",
    "range_min",
    "range_max",
    "color",
    "enabled",
]
RELATIONSHIP_HEADERS = [
    "bundle",
    "from_cell_slug",
    "relationship",
    "to_cell_slug",
    "label",
    "sort_order",
    "enabled",
]
VISUAL_HEADERS = [
    "bundle",
    "cell_slug",
    "visual_type",
    "source_system",
    "source_run_id",
    "source_screen_key",
    "source_item_key",
    "x",
    "y",
    "width",
    "height",
    "sort_order",
    "enabled",
]
SOURCE_HEADERS = [
    "bundle",
    "cell_slug",
    "source_type",
    "source_run_id",
    "source_screen_key",
    "source_component_key",
    "screen_name",
    "component_path",
    "component_name",
    "component_type",
    "bounds_json",
    "raw_json",
]
LIVE_HEADERS = [
    "scope",
    "scope_name",
    "description",
    "card",
    "group",
    "kind",
    "card_order",
    "point",
    "full_path",
    "point_order",
]
TRACE_BASE_HEADERS = ["Chart Scope", "ID", "Name", "display order"]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_optional_csv_rows(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path) if path.exists() else []


def extract_cell_csv_zip(content: bytes, target: Path) -> None:
    max_files = 25
    max_total_bytes = 10 * 1024 * 1024
    total_bytes = 0
    with zipfile.ZipFile(BytesIO(content)) as archive:
        file_count = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            file_count += 1
            if file_count > max_files:
                raise ValueError(f"Cell CSV ZIP exceeds maximum file count of {max_files}")
            if info.flag_bits & 0x1:
                raise ValueError(f"Cell CSV ZIP contains encrypted member: {info.filename}")
            total_bytes += info.file_size
            if total_bytes > max_total_bytes:
                raise ValueError("Cell CSV ZIP exceeds maximum uncompressed size")
            member_path = safe_zip_path(info.filename)
            if member_path.suffix.lower() != ".csv":
                continue
            destination = target.joinpath(*member_path.parts).resolve(strict=False)
            if target.resolve(
                strict=True
            ) not in destination.parents and destination != target.resolve(strict=True):
                raise ValueError(f"Cell CSV ZIP member escapes extraction root: {info.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                output.write(source.read())


def safe_zip_path(filename: str) -> Path:
    normalized = filename.replace("\\", "/")
    path = Path(normalized)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and path.parts[0].endswith(":"))
    ):
        raise ValueError(f"Cell CSV ZIP contains unsafe path: {filename}")
    return path


def find_cell_bundle_dir(root: Path) -> Path:
    if (root / "cells.csv").exists() and (root / "points.csv").exists():
        return root
    for candidate in root.rglob("*"):
        if (
            candidate.is_dir()
            and (candidate / "cells.csv").exists()
            and (candidate / "points.csv").exists()
        ):
            return candidate
    raise ValueError("Cell CSV ZIP requires cells.csv and points.csv")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def trace_headers_for_rows(rows: list[dict[str, Any]]) -> list[str]:
    max_tag = 0
    for row in rows:
        for key in row:
            if key.startswith("Tag "):
                max_tag = max(max_tag, parse_int(key.removeprefix("Tag ")))
    return [*TRACE_BASE_HEADERS, *(f"Tag {index}" for index in range(1, max_tag + 1))]


def required(row: dict[str, str], key: str, row_number: int) -> str:
    value = value_or(row, key, "")
    if value == "":
        raise ValueError(f"Row {row_number}: {key} is required")
    return value


def get_cell(bundle_key: str, cell_slug: str, row_number: int) -> Cell:
    try:
        return Cell.objects.select_related("bundle").get(
            bundle__key=bundle_key, slug=cell_slug
        )
    except Cell.DoesNotExist as exc:
        raise ValueError(
            f"Row {row_number}: references unknown cell {bundle_key}/{cell_slug}"
        ) from exc


def value_or(row: dict[str, str], key: str, default: str) -> str:
    value = row.get(key, default)
    return str(value if value is not None else default).strip()


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str) -> int:
    try:
        return int(float(str(value or "0")))
    except ValueError:
        return 0


def parse_float_or_none(value: str) -> float | None:
    if str(value).strip() == "":
        return None


def parse_json_object(value: str) -> dict[str, Any]:
    if str(value).strip() == "":
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def mine_run_or_none(value: str) -> MineRun | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return MineRun.objects.filter(pk=int(value)).first()
    except ValueError:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def validate_tag_path(value: str, row_number: int) -> None:
    if not value.startswith("[") or "]" not in value or value.endswith("]"):
        raise ValueError(f"Row {row_number}: full_path must look like [provider]path")


def row_sha256(row: dict[str, str]) -> str:
    material = "\0".join(f"{key}={row.get(key, '')}" for key in sorted(row))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def safe_slug(value: str, fallback: str) -> str:
    return slugify(value or fallback)[:120] or fallback


def normalized_tag_path(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        normalized = normalized[1:-1].strip()
    return (
        normalized
        if normalized.startswith("[") and "]" in normalized and not normalized.endswith("]")
        else ""
    )


def point_label(reference) -> str:
    if reference.member_path:
        return f"{reference.base_tag}.{reference.member_path}"
    return reference.base_tag or reference.raw_tag_path or reference.original


def is_control_component(component_type: str) -> bool:
    normalized = component_type.replace("_", "").replace("-", "").lower()
    return any(
        token in normalized
        for token in ("button", "pushbutton", "momentary", "maintained", "input")
    )
