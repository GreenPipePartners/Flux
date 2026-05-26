from pathlib import Path

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from flux_build.hmi.symbolic import classify_component

from flux.cell.services import create_cell_draft_from_hmi_components
from flux.mine.models import MineRun
from flux.web_pulse import display_pulse_context, latest_timestamp

from .models import BuildRun, HmiMapSelection
from .services import (
    build_hmi_symbolic_map_from_mine_run,
    default_hmi_demo_sqlite_path,
    seed_hmi_demo_build_sample,
)


def index(request):
    latest_run = BuildRun.objects.order_by("-created_at").first()
    status = latest_run.status if latest_run else "warning"
    platform_status = {
        "state": "ok" if status == BuildRun.Status.COMPLETE else "warning",
        "label": status.title(),
    }
    cell_count = BuildRun.objects.filter(status=BuildRun.Status.COMPLETE).count()
    latest_hmi_run = (
        MineRun.objects.filter(
            source_type=MineRun.SourceType.FACTORYTALK, status=MineRun.Status.COMPLETE
        )
        .order_by("-created_at")
        .first()
    )
    hmi_components = []
    screen_summaries = []
    component_type_rows = []
    tag_source_rows = []
    default_cell_name = "Recovered HMI Cell"
    if latest_hmi_run is not None:
        hmi_components = list(tagged_hmi_components(latest_hmi_run)[:200])
        for component in hmi_components:
            _category, component.map_symbol = classify_component(
                component.component_type, component.global_object_reference
            )
        screen_summaries = list(latest_hmi_run.hmi_screens.order_by("id")[:12])
        component_type_rows = list(
            latest_hmi_run.hmi_components.values("component_type")
            .annotate(count=Count("id"))
            .order_by("-count", "component_type")[:10]
        )
        tag_source_rows = list(
            latest_hmi_run.hmi_tag_references.values("source_kind")
            .annotate(count=Count("id"))
            .order_by("-count", "source_kind")[:8]
        )
        default_cell_name = latest_hmi_run.label or default_cell_name
    return render(
        request,
        "build/index.html",
        {
            "platform_status": {
                "state": platform_status["state"],
                "label": platform_status["label"],
            },
            "cell_count": cell_count,
            "latest_hmi_run": latest_hmi_run,
            "latest_build_run": latest_run,
            "latest_artifacts": latest_run.artifacts.all()[:6] if latest_run else [],
            "hmi_components": hmi_components,
            "map_screens": build_map_screens(hmi_components),
            "tagged_component_count": tagged_hmi_components(latest_hmi_run).count()
            if latest_hmi_run
            else 0,
            "screen_summaries": screen_summaries,
            "component_type_rows": component_type_rows,
            "tag_source_rows": tag_source_rows,
            "default_hmi_map_output_dir": "/tmp/opencode/flux-hmi-map",
            "default_cell_bundle_key": f"hmi-run-{latest_hmi_run.id}"
            if latest_hmi_run
            else "hmi-run",
            "default_cell_name": default_cell_name,
            "sample_hmi_demo_available": default_hmi_demo_sqlite_path().exists(),
            "sample_hmi_demo_path": default_hmi_demo_sqlite_path(),
            "flux_web_pulse": display_pulse_context(
                source_label="Flux.build run state",
                last_backend_at=latest_timestamp(
                    value.updated_at for value in (latest_run, latest_hmi_run) if value is not None
                ),
                state=platform_status["state"],
                detail="%s cells built" % cell_count,
            ),
        },
    )


@require_POST
def seed_hmi_demo(request):
    try:
        build_run = seed_hmi_demo_build_sample()
    except Exception as exc:
        messages.error(request, f"HMI demo sample seed failed: {exc}")
        return redirect("build:index")
    messages.success(
        request,
        "Seeded HMI demo build sample with %(screens)s screens and %(components)s components."
        % {
            "screens": build_run.summary.get("screen_count", 0),
            "components": build_run.summary.get("component_count", 0),
        },
    )
    return redirect("build:index")


@require_POST
def build_hmi_map(request):
    mine_run_id = request.POST.get("mine_run_id")
    action = request.POST.get("action") or "generate_map"
    output_dir = request.POST.get("output_dir") or "/tmp/opencode/flux-hmi-map"
    selected_component_ids = [
        int(value) for value in request.POST.getlist("component_id") if value.isdigit()
    ]
    if not mine_run_id:
        messages.error(request, "Choose an HMI mine run before building a symbolic map.")
        return redirect("build:index")
    mine_run = MineRun.objects.get(pk=mine_run_id)
    HmiMapSelection.objects.filter(mine_run=mine_run).delete()
    selected_components = tagged_hmi_components(mine_run).filter(id__in=selected_component_ids)
    selected_component_ids = list(selected_components.values_list("id", flat=True))
    for component in selected_components.select_related("screen"):
        HmiMapSelection.objects.create(
            mine_run=mine_run, screen=component.screen, component=component, enabled=True
        )
    if action == "create_cell_draft":
        try:
            result = create_cell_draft_from_hmi_components(
                mine_run,
                selected_component_ids,
                bundle_key=request.POST.get("cell_bundle_key") or f"hmi-run-{mine_run.id}",
                bundle_name=request.POST.get("cell_bundle_name") or f"HMI Run {mine_run.id}",
                cell_slug=request.POST.get("cell_slug") or "selected-hmi-cell",
                cell_name=request.POST.get("cell_name") or "Selected HMI Cell",
                group=request.POST.get("cell_group") or "",
                kind=request.POST.get("cell_kind") or "Recovered",
            )
        except Exception as exc:
            messages.error(request, f"Cell draft creation failed: {exc}")
            return redirect("build:index")
        messages.success(
            request,
            f"Created cell draft {result.cell.name} with {result.sources} sources and {result.points} points.",
        )
        return redirect("build:index")
    try:
        run = build_hmi_symbolic_map_from_mine_run(mine_run.id, Path(output_dir))
    except Exception as exc:
        messages.error(request, f"HMI map build failed: {exc}")
        return redirect("build:index")
    messages.success(
        request,
        f"Built HMI symbolic map {run.id} with {run.summary.get('component_count', 0)} components.",
    )
    return redirect("build:index")


def tagged_hmi_components(mine_run: MineRun):
    return (
        mine_run.hmi_components.select_related("screen")
        .prefetch_related("tag_references")
        .annotate(tag_reference_total=Count("tag_references"))
        .filter(tag_reference_total__gt=0)
        .order_by("screen__id", "id")
    )


def build_map_screens(components) -> list[dict]:
    screens: dict[int, dict] = {}
    for component in components:
        screen = component.screen
        if screen.id not in screens:
            screens[screen.id] = {
                "screen": screen,
                "width": screen.width or 1024,
                "height": screen.height or 768,
                "nodes": [],
            }
        screens[screen.id]["nodes"].append(build_map_node(component, screens[screen.id]))
    return list(screens.values())


def build_map_node(component, screen_context: dict) -> dict:
    bounds = component.bounds or {}
    screen_width = float(screen_context["width"] or 1024)
    screen_height = float(screen_context["height"] or 768)
    left = safe_float(bounds.get("left"), 0.0)
    top = safe_float(bounds.get("top"), 0.0)
    width = safe_float(bounds.get("width"), 28.0)
    height = safe_float(bounds.get("height"), 24.0)
    _category, symbol = classify_component(
        component.component_type, component.global_object_reference
    )
    return {
        "component": component,
        "symbol": symbol,
        "left_pct": clamp_percent(((left + width / 2) / screen_width) * 100),
        "top_pct": clamp_percent(((top + height / 2) / screen_height) * 100),
        "width_pct": clamp_percent((width / screen_width) * 100, minimum=2.4, maximum=12.0),
        "height_pct": clamp_percent((height / screen_height) * 100, minimum=2.4, maximum=9.0),
    }


def safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp_percent(value: float, *, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return round(max(minimum, min(maximum, value)), 3)
