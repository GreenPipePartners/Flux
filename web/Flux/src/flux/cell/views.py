from __future__ import annotations

import csv
from io import StringIO

from django.conf import settings
from django.db.models import Max
from django.http import HttpResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from flux.base.runtime import RuntimeTag, TagSample
from flux.plane.models import Sample
from flux.spot.selectors import format_live_value
from flux.pagination import table_page
from flux.serve.status import runtime_read_status
from flux.trace.models import TraceSignal
from flux.web_pulse import display_pulse_context, latest_timestamp

from .models import Bundle, Cell, Comment
from .services import (
    CELL_HEADERS,
    LIVE_HEADERS,
    POINT_HEADERS,
    RELATIONSHIP_HEADERS,
    SOURCE_HEADERS,
    VISUAL_HEADERS,
    cell_rows,
    live_scope_rows,
    point_rows,
    relationship_rows,
    source_rows,
    trace_headers_for_rows,
    trace_scope_rows,
    visual_rows,
    import_cell_bundle_zip_bytes,
    seed_demo_cell_bundle,
)


def index(request):
    card_context = process_card_context()
    bundles_qs = Bundle.objects.prefetch_related("cells").order_by("key")
    bundles_page = table_page(request, bundles_qs, "bundles_page")
    bundle_count = Bundle.objects.count()
    cell_count = Cell.objects.count()
    return render(
        request,
        "cell/index.html",
        {
            "bundle_count": bundle_count,
            "cell_count": cell_count,
            "bundles": bundles_page.object_list,
            "bundles_page": bundles_page,
            "cell_cards": card_context["cell_cards"],
            "flux_web_pulse": display_pulse_context(
                source_label="Flux.cell draft state",
                last_backend_at=latest_timestamp(
                    (
                        Bundle.objects.aggregate(latest=Max("updated_at"))["latest"],
                        Cell.objects.aggregate(latest=Max("updated_at"))["latest"],
                    )
                ),
                state="ok" if cell_count else "unknown",
                detail=f"{cell_count} draft cells · {bundle_count} bundles",
            ),
        },
    )


def phone_demo(request):
    context = process_card_context()
    context["embed_mode"] = True
    return render(
        request,
        "cell/phone_demo.html",
        context,
    )


def process_card_context() -> dict:
    cells = list(
        Cell.objects.filter(enabled=True)
        .select_related("bundle")
        .prefetch_related(
            "points",
            "visuals",
            "sources",
            "comments",
            "outgoing_relationships__to_cell",
            "incoming_relationships__from_cell",
        )[:80]
    )
    runtime_context = runtime_context_for_cells(cells)
    return {
        "cells": cells,
        "cell_cards": [cell_card_context(cell, runtime_context=runtime_context) for cell in cells],
    }


@require_POST
def import_bundle(request):
    upload = request.FILES.get("bundle_zip")
    replace = request.POST.get("replace") == "on"
    if upload is None:
        messages.error(request, "Choose a Flux.cell CSV ZIP bundle to import.")
        return redirect("cell:index")
    try:
        result = import_cell_bundle_zip_bytes(upload.name, upload.read(), replace=replace)
    except Exception as exc:
        messages.error(request, f"Cell CSV import failed: {exc}")
        return redirect("cell:index")
    messages.success(
        request, f"Imported {result.cells} cells and {result.points} points from {upload.name}."
    )
    return redirect("cell:index")


@require_POST
def seed_demo(request):
    result = seed_demo_cell_bundle()
    messages.success(
        request,
        f"Seeded {result.bundle.name}: {result.cells} cells, {result.points} points, {result.runtime_tags} runtime tags.",
    )
    return redirect(result.anchor_url)


@require_POST
def add_comment(request, bundle_key: str, cell_slug: str):
    cell = get_object_or_404(Cell, bundle__key=bundle_key, slug=cell_slug)
    body = (request.POST.get("body") or "").strip()
    author = (request.POST.get("author_name") or "").strip()
    if not body:
        messages.error(request, "Comment cannot be empty.")
        return redirect("cell:index")
    Comment.objects.create(cell=cell, body=body, author_name=author)
    messages.success(request, f"Added comment to {cell.name}.")
    return redirect("cell:index")


def live_scope_csv(request, bundle_key: str):
    return csv_response(f"{bundle_key}-live-scope.csv", live_scope_rows(bundle_key), LIVE_HEADERS)


def cells_csv(request, bundle_key: str):
    return csv_response("cells.csv", cell_rows(bundle_key), CELL_HEADERS)


def points_csv(request, bundle_key: str):
    return csv_response("points.csv", point_rows(bundle_key), POINT_HEADERS)


def relationships_csv(request, bundle_key: str):
    return csv_response("relationships.csv", relationship_rows(bundle_key), RELATIONSHIP_HEADERS)


def visuals_csv(request, bundle_key: str):
    return csv_response("visuals.csv", visual_rows(bundle_key), VISUAL_HEADERS)


def sources_csv(request, bundle_key: str):
    return csv_response("sources.csv", source_rows(bundle_key), SOURCE_HEADERS)


def trace_scopes_csv(request, bundle_key: str):
    rows = trace_scope_rows(bundle_key)
    return csv_response(f"{bundle_key}-trace-scopes.csv", rows, trace_headers_for_rows(rows))


def csv_response(filename: str, rows: list[dict], fieldnames: list[str]) -> HttpResponse:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def cell_card_context(cell: Cell, *, runtime_context: dict[str, dict]) -> dict:
    points = list(cell.points.all())
    live_points = [point for point in points if point.enabled and point.include_live][:5]
    chart_points = [point for point in points if point.enabled and point.include_trace][:8]
    visuals = [visual for visual in cell.visuals.all() if visual.enabled]
    latest_comment = next(iter(cell.comments.all()), None)
    outgoing = [
        relationship for relationship in cell.outgoing_relationships.all() if relationship.enabled
    ]
    incoming = [
        relationship for relationship in cell.incoming_relationships.all() if relationship.enabled
    ]
    parent = first_relationship_target(outgoing, "parent") or first_relationship_source(
        incoming, "child"
    )
    children = [
        relationship.to_cell
        for relationship in outgoing
        if relationship.relationship_type == "child"
    ][:3]
    if not children:
        children = [
            relationship.from_cell
            for relationship in incoming
            if relationship.relationship_type == "parent"
        ][:3]
    return {
        "cell": cell,
        "live_points": [live_point_context(point, runtime_context) for point in live_points],
        "chart_points": [chart_point_context(point, runtime_context) for point in chart_points],
        "latest_comment": latest_comment,
        "visual": visuals[0] if visuals else None,
        "source_count": cell.sources.count(),
        "parent": parent,
        "children": children,
        "prev_area": first_relationship_target(outgoing, "prev_area"),
        "next_area": first_relationship_target(outgoing, "next_area"),
    }


def first_relationship_target(relationships, relationship_type: str):
    return next(
        (
            relationship.to_cell
            for relationship in relationships
            if relationship.relationship_type == relationship_type
        ),
        None,
    )


def first_relationship_source(relationships, relationship_type: str):
    return next(
        (
            relationship.from_cell
            for relationship in relationships
            if relationship.relationship_type == relationship_type
        ),
        None,
    )


def runtime_context_for_cells(cells: list[Cell]) -> dict[str, dict]:
    full_paths = sorted(
        {
            point.full_path
            for cell in cells
            for point in cell.points.all()
            if point.enabled and point.full_path
        }
    )
    tags_by_path = runtime_tags_by_full_path(full_paths)
    sample_map = latest_samples_by_path(tags_by_path)
    now = timezone.now()
    return {
        "tags_by_path": tags_by_path,
        "samples_by_path": sample_map,
        "now": now,
    }


def runtime_tags_by_full_path(full_paths: list[str]) -> dict[str, RuntimeTag]:
    keys = []
    for full_path in full_paths:
        try:
            keys.append(parse_full_tag_path(full_path))
        except ValueError:
            continue
    if not keys:
        return {}
    providers = {provider for provider, _path in keys}
    paths = {path for _provider, path in keys}
    exact = {(provider, path) for provider, path in keys}
    tags = RuntimeTag.objects.select_related("latest_value", "schedule").filter(
        enabled=True, provider__in=providers, path__in=paths
    )
    return {tag.full_path: tag for tag in tags if (tag.provider, tag.path) in exact}


def latest_samples_by_path(tags_by_path: dict[str, RuntimeTag]) -> dict[str, list[dict]]:
    samples: dict[str, list[dict]] = {}
    signals_by_tag_id = {
        signal.tag_id: signal
        for signal in TraceSignal.objects.filter(
            tag__in=tags_by_path.values(), cache_enabled=True, profile__enabled=True
        ).select_related("series").order_by("profile__key", "sort_order", "id")
    }
    for full_path, tag in tags_by_path.items():
        signal = signals_by_tag_id.get(tag.id)
        if signal is not None and signal.series_id is not None:
            cache_points = list(
                Sample.objects.filter(series_id=signal.series_id).order_by("-timestamp")[:8]
            )
            if cache_points:
                samples[full_path] = [
                    {
                        "value": point.value_float,
                        "timestamp": point.timestamp,
                        "source": "plane samples",
                    }
                    for point in cache_points
                ]
                continue
        samples[full_path] = [
            {"value": sample.value, "timestamp": sample.read_at, "source": "runtime samples"}
            for sample in TagSample.objects.filter(tag=tag).order_by("-read_at")[:8]
        ]
    return samples


def live_point_context(point, runtime_context: dict[str, dict]) -> dict:
    tag = runtime_context["tags_by_path"].get(point.full_path)
    latest = getattr(tag, "latest_value", None) if tag is not None else None
    status = runtime_read_status(
        latest, now=runtime_context["now"], stale_after_seconds=settings.STALE_AFTER_SECONDS
    )
    units = point.engineering_units or (tag.engineering_units if tag is not None else "")
    return {
        "point": point,
        "label": point.label,
        "display_value": format_live_value(latest.value if latest is not None else None) or "--",
        "units": units,
        "quality": latest.quality_code if latest is not None else "Missing",
        "read_at": latest.read_at if latest is not None else None,
        "state": "ok"
        if status.online and not status.stale and not status.bad_quality
        else "warning"
        if latest is not None
        else "missing",
    }


def chart_point_context(point, runtime_context: dict[str, dict]) -> dict:
    samples = list(reversed(runtime_context["samples_by_path"].get(point.full_path, [])))
    numeric_values = [
        float(sample["value"])
        for sample in samples
        if isinstance(sample["value"], int | float) and not isinstance(sample["value"], bool)
    ]
    latest = numeric_values[-1] if numeric_values else None
    normalized_points = normalize_values(numeric_values)
    return {
        "point": point,
        "label": point.label,
        "sample_count": len(samples),
        "latest_value": format_live_value(latest) if latest is not None else "--",
        "source_label": samples[-1]["source"] if samples else "no cache",
        "normalized_points": normalized_points,
        "sparkline_points": sparkline_points(normalized_points),
    }


def normalize_values(values: list[float]) -> list[int]:
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        return [50 for _value in values]
    return [round(((value - minimum) / (maximum - minimum)) * 100) for value in values]


def sparkline_points(normalized_values: list[int]) -> str:
    if not normalized_values:
        return ""
    if len(normalized_values) == 1:
        return "0,50 100,50"
    x_step = 100 / (len(normalized_values) - 1)
    return " ".join(
        f"{index * x_step:.1f},{100 - value:.1f}" for index, value in enumerate(normalized_values)
    )


def parse_full_tag_path(full_path: str) -> tuple[str, str]:
    if not full_path.startswith("[") or "]" not in full_path:
        raise ValueError("canonical tag references must be full [provider]path values")
    provider, path = full_path[1:].split("]", 1)
    if not provider or not path:
        raise ValueError("canonical tag references must be full [provider]path values")
    return provider, path
