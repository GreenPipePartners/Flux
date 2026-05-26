import json

from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from flux.chart.annotations import TraceAnnotationError, query_saved_annotations, store_annotation
from flux.chart.control import (
    RESERVED_CHART_PROFILE_PATHS,
    fluxolot_chart,
    fluxolot_context,
    fluxolot_payload_json,
    fluxolot_source_options,
    nav_well_chart,
    nav_well_context,
    nav_well_payload_json,
    nav_well_source_options,
    profile_payload_json,
    profile_trace_chart,
    touch_trace_profile_demand,
    trace_embed_mode,
    trace_step_minutes,
    trace_window_max_minutes,
    trace_window_minutes,
)
from flux.chart.providers.nav_wells import WELL_TRACE_PROFILE_PREFIX
from flux.links import flux_link
from flux.pagination import TABLE_PAGE_SIZE, table_page
from flux.plane.samples import recent_sample_queryset
from flux.sim.fluxolot_fishtank import FLUXOLOT_TANKS, fluxolot_trace_profile_key
from flux.trace.models import TraceProfile

from .selectors import trace_sample_series


TRACE_PATHS_PAGE_SIZE = TABLE_PAGE_SIZE


@ensure_csrf_cookie
def index(request):
    sample_qs = recent_sample_queryset()
    sample_page = table_page(request, sample_qs, "samples_page")
    samples = list(sample_page.object_list)
    sample_groups = trace_sample_groups(samples)
    trace_chart = trace_sample_series()
    return render(
        request,
        "trace/index.html",
        {
            "samples": samples,
            "sample_page": sample_page,
            "sample_total_count": sample_page.paginator.count,
            "sample_groups": sample_groups,
            "trace_samples_link": trace_samples_link(request, sample_groups, samples),
            "trace_chart": trace_chart,
            **trace_link_context(request, trace_chart, title="Historical Tag Charts"),
        },
    )


def trace_path_index() -> list[dict[str, str | int]]:
    paths: list[dict[str, str | int]] = [
        {
            "label": "Historical Tag Charts",
            "path": reverse("chart:index"),
            "description": "Generic historical trend from recent numeric Plane samples.",
            "detail": "Built-in",
        },
        {
            "label": "Streaming Charts",
            "path": reverse("chart:stream"),
            "description": "Right-edge-follow trend that polls fresh Plane samples.",
            "detail": "Built-in",
        },
        {
            "label": "Navigation Well Charts",
            "path": reverse("chart:nav-well-trace"),
            "description": "Rotating multi-well cached trace surface.",
            "detail": "Built-in",
        },
        {
            "label": "Fluxolot Fishtank Charts",
            "path": reverse("chart:fluxolot-trace"),
            "description": "Fluxolot proof surface cycling Sir and Missus tanks.",
            "detail": "Built-in",
        },
    ]
    profiles = TraceProfile.objects.filter(enabled=True).annotate(signal_count=Count("signals", distinct=True)).order_by("key")
    for profile in profiles:
        if consolidated_trace_profile(profile.key):
            continue
        route_name = "chart:cache-profile" if profile.key in RESERVED_CHART_PROFILE_PATHS else "chart:scope-profile"
        paths.append(
            {
                "label": profile.label,
                "path": reverse(route_name, args=[profile.key]),
                "description": f"Chart profile `{profile.key}` cached for {profile.cache_window_minutes} minutes.",
                "detail": f"{profile.signal_count} signals",
            }
        )
    return paths


def trace_profile_path(profile: TraceProfile) -> str:
    if profile.key.startswith(f"{WELL_TRACE_PROFILE_PREFIX}-"):
        return reverse("chart:nav-well-trace")
    if profile.key in {fluxolot_trace_profile_key(tank) for tank in FLUXOLOT_TANKS}:
        return reverse("chart:fluxolot-trace")
    if profile.key in RESERVED_CHART_PROFILE_PATHS:
        return reverse("chart:cache-profile", args=[profile.key])
    return reverse("chart:scope-profile", args=[profile.key])


def trace_sample_groups(samples: list[object]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    default_path = reverse("chart:index")
    for sample in samples:
        signals = list(sample.series.chart_signals.all())
        if not signals:
            add_trace_sample_group(groups, default_path, "Historical Tag Charts", "Plane samples", sample)
            continue
        for signal in signals:
            profile = signal.profile
            add_trace_sample_group(groups, trace_profile_path(profile), profile.label, f"Chart profile `{profile.key}`", sample)
    return sorted(groups.values(), key=lambda group: group["latest_read"], reverse=True)


def add_trace_sample_group(
    groups: dict[str, dict[str, object]],
    path: str,
    label: str,
    detail: str,
    sample: object,
) -> None:
    group = groups.setdefault(
        path,
        {
            "path": path,
            "label": label,
            "detail": detail,
            "samples": [],
            "sample_count": 0,
            "latest_read": sample.timestamp,
        },
    )
    group["samples"].append(sample)
    group["sample_count"] += 1
    if sample.timestamp > group["latest_read"]:
        group["latest_read"] = sample.timestamp


def trace_samples_link(request, sample_groups: list[dict[str, object]], samples: list[object]):
    rows = [("Recent samples", len(samples)), ("Chart links", len(sample_groups))]
    rows.extend((str(group["label"]), f'{group["sample_count"]} samples @ {group["path"]}') for group in sample_groups)
    return flux_link(
        title="Flux Chart Samples",
        description="Recent Plane samples grouped by the Flux.chart route that owns each signal.",
        rows=rows,
        payload={
            "type": "flux.chart.samples.context",
            "sample_count": len(samples),
            "chart_links": [group["path"] for group in sample_groups],
        },
        docs_path="apps/chart/",
        page_url=request.build_absolute_uri(),
    )


def trace_platform_status(trace_chart: dict, trace_paths: list[dict[str, str | int]]) -> dict[str, str]:
    if trace_chart.get("series") or len(trace_paths) > 4:
        return {"state": "ok", "label": "Ready"}
    return {"state": "warning", "label": "Attention needed"}


def consolidated_trace_profile(profile_key: str) -> bool:
    if profile_key.startswith(f"{WELL_TRACE_PROFILE_PREFIX}-"):
        return True
    return profile_key in {fluxolot_trace_profile_key(tank) for tank in FLUXOLOT_TANKS}


@ensure_csrf_cookie
def cache_profile(request, profile_key: str):
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
    trace_chart = profile_trace_chart(profile)
    return render_profile_chart(
        request,
        profile=profile,
        trace_chart=trace_chart,
        subtitle="Rolling historian cache from Flux.chart significance config. This page reads local Plane samples only.",
        badge="chart cache",
        payload_url=f"/chart/cache/{profile.key}/payload/",
    )


def cache_profile_payload(request, profile_key: str):
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
    payload_json = profile_payload_json(profile, window_minutes=profile.cache_window_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response({"traceChart": profile_trace_chart(profile), "traceError": ""})


@ensure_csrf_cookie
def scope_profile(request, scope: str):
    profile = get_object_or_404(TraceProfile, key=scope, enabled=True)
    trace_chart = profile_trace_chart(profile)
    return render_profile_chart(
        request,
        profile=profile,
        trace_chart=trace_chart,
        subtitle="CSV-defined Flux.chart scope backed by the selected TraceProfile.",
        badge=scope,
        payload_url=f"/chart/{profile.key}/payload/",
    )


def scope_profile_payload(request, scope: str):
    profile = get_object_or_404(TraceProfile, key=scope, enabled=True)
    payload_json = profile_payload_json(profile, window_minutes=profile.cache_window_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response({"traceChart": profile_trace_chart(profile), "traceError": ""})


def render_profile_chart(request, *, profile: TraceProfile, trace_chart: dict, subtitle: str, badge: str, payload_url: str):
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "sample_groups": [],
            "trace_chart": trace_chart,
            "trace_error": "",
            "trace_title": profile.label,
            "trace_subtitle": subtitle,
            "trace_badge": badge,
            "trace_payload_url": payload_url,
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Drag selects an x-range to zoom. Shift-drag pans. Wheel zooms; side-scroll pans.",
            **trace_link_context(request, trace_chart, title=profile.label),
        },
    )


@ensure_csrf_cookie
def fluxolot_trace(request):
    profile, tank, tank_count, set_index = fluxolot_context(request)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    trace_chart = fluxolot_chart(profile, tank=tank, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "sample_groups": [],
            "trace_chart": trace_chart,
            "trace_error": "" if profile else "No Fluxolot trace profiles seeded yet.",
            "trace_title": "Fluxolot Fishtank Charts",
            "trace_subtitle": "One Flux.chart proof surface cycling between Sir and Missus Fluxolot tank history.",
            "trace_badge": trace_chart.get("setLabel") or "fluxolot",
            "trace_cycle_url": "/chart/fluxolot/payload/",
            "trace_set_count": tank_count,
            "trace_cycle_label": "Tank",
            "trace_source_options": fluxolot_source_options(),
            "trace_window_minutes": window_minutes,
            "trace_window_max_minutes": trace_window_max_minutes(profile),
            "trace_step_minutes": step_minutes,
            "trace_live_refresh_seconds": 15,
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Use Previous/Next Tank or left/right arrow keys to cycle Sir and Missus Fluxolot.",
            **trace_link_context(request, trace_chart, title="Fluxolot Fishtank Charts"),
        },
    )


def fluxolot_trace_payload(request):
    profile, tank, _tank_count, set_index = fluxolot_context(request)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    payload_json = fluxolot_payload_json(profile, tank=tank, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response(
        {
            "traceChart": fluxolot_chart(profile, tank=tank, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes),
            "traceError": "" if profile else "No Fluxolot trace profiles seeded yet.",
        }
    )


@ensure_csrf_cookie
def nav_well_trace(request):
    profile, well, well_count, set_index = nav_well_context(request)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    trace_chart = nav_well_chart(profile, well=well, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
    embed = trace_embed_mode(request)
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "sample_groups": [],
            "trace_chart": trace_chart,
            "trace_error": "" if profile else "No navigation well trace profiles seeded yet.",
            "trace_title": "Navigation Well Charts",
            "trace_subtitle": "One generic Charts page cycling through navigation wells. Each well swaps to its own 8 local cached chart signals.",
            "trace_badge": trace_chart.get("setLabel") or "nav wells",
            "trace_cycle_url": "/chart/wells/payload/",
            "trace_set_count": well_count,
            "trace_cycle_label": "Well",
            "trace_source_options": nav_well_source_options(),
            "trace_window_minutes": window_minutes,
            "trace_window_max_minutes": trace_window_max_minutes(profile),
            "trace_step_minutes": step_minutes,
            "trace_live_refresh_seconds": 60,
            "trace_embed": embed,
            "embed_mode": embed,
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Drag selects an x-range to zoom. Shift-drag pans. Wheel zooms; side-scroll pans. Use Previous/Next Well or left/right arrow keys to cycle wells.",
            **trace_link_context(request, trace_chart, title="Navigation Well Charts"),
        },
    )


def nav_well_trace_payload(request):
    profile, well, _well_count, set_index = nav_well_context(request)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    payload_json = nav_well_payload_json(profile, well=well, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response(
        {
            "traceChart": nav_well_chart(profile, well=well, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes),
            "traceError": "" if profile else "No navigation well trace profiles seeded yet.",
        }
    )


@ensure_csrf_cookie
def nav_well_trace_embed(request):
    return nav_well_trace(request)


def trace_json_response(payload: dict) -> HttpResponse:
    return JsonResponse(payload)


@require_POST
def demand(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    profile_key = str(payload.get("profileKey") or "").strip()
    if not profile_key:
        return JsonResponse({"ok": False, "error": "profileKey required"}, status=400)
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
    return JsonResponse({"ok": True, "touched": touch_trace_profile_demand(profile)})


def annotations(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    try:
        result = store_annotation(payload)
    except TraceAnnotationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=502)
    return JsonResponse({"ok": True, **result})


def query_annotations(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
    try:
        result = query_saved_annotations(payload)
    except TraceAnnotationError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=502)
    return JsonResponse({"ok": True, **result})


def trace_link_context(request, trace_chart: dict, *, title: str) -> dict[str, dict[str, str]]:
    series = trace_chart.get("series") or []
    all_trace_paths = trace_path_index()
    trace_path_page = table_page(request, all_trace_paths, "paths_page", per_page=TRACE_PATHS_PAGE_SIZE)
    trace_paths = list(trace_path_page.object_list)
    surface_modes = trace_surface_modes(request)
    rows = [
        ("Title", title),
        ("Source", trace_chart.get("source", "runtime-samples")),
        ("Series count", len(series)),
        ("Window", trace_chart.get("windowLabel", "-")),
        ("Latest read", trace_chart.get("latestReadAt", "-")),
    ]
    link = flux_link(
        title="Flux Chart Trend",
        description="Flux Chart context describes the current trend source, window, visible series, and local cache/historian boundary.",
        rows=rows,
        payload={"type": "flux.chart.trend.context", "profile_key": trace_chart.get("profileKey"), "series_count": len(series)},
        docs_path="apps/chart/",
        page_url=request.build_absolute_uri(),
    )
    return {
        "trace_page_link": link,
        "trace_chart_link": link,
        "trace_paths": trace_paths,
        "trace_path_page": trace_path_page,
        "trace_path_total": len(all_trace_paths),
        "trace_path_page_size": TRACE_PATHS_PAGE_SIZE,
        "platform_status": trace_platform_status(trace_chart, all_trace_paths),
        **surface_modes,
    }


def trace_surface_modes(request) -> dict[str, str]:
    default_card = "" if request.resolver_match.url_name == "index" else "trace-chart"
    selected_card = request.GET.get("card") or default_card
    if selected_card not in {"trace-paths", "trace-chart", "trace-samples"}:
        selected_card = ""
    default_mode = "detail" if selected_card == "trace-chart" and default_card else "summary"
    requested_mode = request.GET.get("mode", default_mode)
    trace_paths_mode = requested_mode if selected_card == "trace-paths" and requested_mode == "detail" else "summary"
    trace_chart_mode = requested_mode if selected_card == "trace-chart" and requested_mode in {"detail", "configure"} else "summary"
    trace_samples_mode = requested_mode if selected_card == "trace-samples" and requested_mode == "detail" else "summary"
    surface_mode = next(
        (mode for mode in (trace_paths_mode, trace_chart_mode, trace_samples_mode) if mode != "summary"),
        "summary",
    )
    return {
        "selected_trace_card": selected_card,
        "trace_surface_mode": surface_mode,
        "trace_paths_mode": trace_paths_mode,
        "trace_chart_mode": trace_chart_mode,
        "trace_samples_mode": trace_samples_mode,
    }


def stream(request):
    trace_chart = trace_sample_series(samples_per_tag=120)
    return render(
        request,
        "trace/live.html",
        {
            "trace_chart": trace_chart,
            "poll_seconds": 5,
            "window_minutes": 15,
            **trace_link_context(request, trace_chart, title="Streaming Tag Charts"),
        },
    )


def stream_samples(request):
    since = parse_datetime(request.GET.get("since", ""))
    return JsonResponse(trace_sample_series(samples_per_tag=120, since=since))
