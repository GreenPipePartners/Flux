import json

import orjson
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.dateparse import parse_datetime

from flux.base.runtime import TagSample
from flux.links import flux_link
from flux.nav.registry import NavigationOption
from flux.opt.services import lease_runtime_demand
from flux.sim.fluxolot_fishtank import FLUXOLOT_TANKS, FLUXOLOT_TRACE_SCOPE, fluxolot_trace_profile_key
from flux.trace.models import TraceProfile
from trace.annotations import TraceAnnotationError, query_saved_annotations, store_annotation
from trace.cache import trace_cache_payload
from trace.data_plane import postgres_trace_payload_json
from trace.providers.nav_wells import WELL_TRACE_PROFILE_PREFIX, profile_for_well_index
from trace.questdb_data_plane import questdb_trace_payload_json

from .selectors import trace_sample_series


@ensure_csrf_cookie
def index(request):
    samples = TagSample.objects.select_related("tag").order_by("-read_at")[:50]
    trace_chart = trace_sample_series()
    return render(
        request,
        "trace/index.html",
        {
            "samples": samples,
            "trace_chart": trace_chart,
            **trace_link_context(request, trace_chart, title="Historical Tag Trace"),
        },
    )


@ensure_csrf_cookie
def cache_profile(request, profile_key: str):
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
    lease_trace_profile_demand(profile)
    trace_chart = trace_cache_payload(profile)
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "trace_chart": trace_chart,
            "trace_error": "",
            "trace_title": profile.label,
            "trace_subtitle": "Rolling historian cache from Flux Trace significance config. This page reads local TraceCachePoint rows only.",
            "trace_badge": "trace cache",
            "trace_payload_url": f"/trace/cache/{profile.key}/payload/",
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Drag selects an x-range to zoom. Shift-drag pans. Wheel zooms; side-scroll pans.",
            **trace_link_context(request, trace_chart, title=profile.label),
        },
    )


def cache_profile_payload(request, profile_key: str):
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
    lease_trace_profile_demand(profile)
    payload_json = postgres_trace_payload_json(profile_id=profile.id, window_minutes=profile.cache_window_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response({"traceChart": trace_cache_payload(profile), "traceError": ""})


@ensure_csrf_cookie
def scope_profile(request, scope: str):
    profile = get_object_or_404(TraceProfile, key=scope, enabled=True)
    lease_trace_profile_demand(profile)
    trace_chart = trace_cache_payload(profile)
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "trace_chart": trace_chart,
            "trace_error": "",
            "trace_title": profile.label,
            "trace_subtitle": "CSV-defined Flux.trace scope backed by the selected TraceProfile.",
            "trace_badge": scope,
            "trace_payload_url": f"/trace/{profile.key}/payload/",
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Drag selects an x-range to zoom. Shift-drag pans. Wheel zooms; side-scroll pans.",
            **trace_link_context(request, trace_chart, title=profile.label),
        },
    )


def scope_profile_payload(request, scope: str):
    profile = get_object_or_404(TraceProfile, key=scope, enabled=True)
    lease_trace_profile_demand(profile)
    payload_json = postgres_trace_payload_json(profile_id=profile.id, window_minutes=profile.cache_window_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response({"traceChart": trace_cache_payload(profile), "traceError": ""})


@ensure_csrf_cookie
def fluxolot_trace(request):
    profile, tank, tank_count, set_index = fluxolot_context(request)
    lease_trace_profile_demand(profile)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    trace_chart = fluxolot_chart(profile, tank=tank, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "trace_chart": trace_chart,
            "trace_error": "" if profile else "No Fluxolot trace profiles seeded yet.",
            "trace_title": "Fluxolot Fishtank Trace",
            "trace_subtitle": "One Flux.trace proof surface cycling between Sir and Missus Fluxolot tank history.",
            "trace_badge": trace_chart.get("setLabel") or FLUXOLOT_TRACE_SCOPE,
            "trace_cycle_url": "/trace/fluxolot/payload/",
            "trace_set_count": tank_count,
            "trace_cycle_label": "Tank",
            "trace_source_options": fluxolot_source_options(),
            "trace_window_minutes": window_minutes,
            "trace_window_max_minutes": trace_window_max_minutes(profile),
            "trace_step_minutes": step_minutes,
            "trace_live_refresh_seconds": 15,
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Use Previous/Next Tank or left/right arrow keys to cycle Sir and Missus Fluxolot.",
            **trace_link_context(request, trace_chart, title="Fluxolot Fishtank Trace"),
        },
    )


def fluxolot_trace_payload(request):
    profile, tank, _tank_count, set_index = fluxolot_context(request)
    lease_trace_profile_demand(profile)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    if profile:
        payload_json = postgres_trace_payload_json(
            profile_id=profile.id,
            window_minutes=window_minutes,
            step_minutes=step_minutes,
            set_index=set_index,
            set_label=tank.label if tank else profile.label,
            well_id=tank.value if tank else "",
        )
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
    lease_trace_profile_demand(profile)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    trace_chart = nav_well_chart(profile, well=well, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
    embed = trace_embed_mode(request)
    return render(
        request,
        "trace/index.html",
        {
            "samples": [],
            "trace_chart": trace_chart,
            "trace_error": "" if profile else "No navigation well trace profiles seeded yet.",
            "trace_title": "Navigation Well Trace",
            "trace_subtitle": "One generic Trace page cycling through navigation wells. Each well swaps to its own 8 local cached trace signals.",
            "trace_badge": trace_chart.get("setLabel") or "nav wells",
            "trace_cycle_url": "/trace/wells/payload/",
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
            **trace_link_context(request, trace_chart, title="Navigation Well Trace"),
        },
    )


def nav_well_trace_payload(request):
    profile, well, _well_count, set_index = nav_well_context(request)
    lease_trace_profile_demand(profile)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    if profile:
        payload_json = questdb_trace_payload_json(
            profile_id=profile.id,
            window_minutes=window_minutes,
            step_minutes=step_minutes,
            set_index=set_index,
            set_label=well.label if well else profile.label,
            well_id=well.value if well else "",
        )
        if payload_json is not None:
            return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response(
        {
            "traceChart": nav_well_chart(
                profile,
                well=well,
                set_index=set_index,
                window_minutes=window_minutes,
                step_minutes=step_minutes,
            ),
            "traceError": "" if profile else "No navigation well trace profiles seeded yet.",
        }
    )


@ensure_csrf_cookie
def nav_well_trace_embed(request):
    return nav_well_trace(request)


def trace_json_response(payload: dict) -> HttpResponse:
    return JsonResponse(payload)


def lease_trace_profile_demand(profile) -> int:
    if profile is None:
        return 0
    return lease_runtime_demand(tags=(signal.tag for signal in profile.signals.select_related("tag").filter(tag__enabled=True)))


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


def nav_well_context(request):
    source = request.GET.get("source") or request.GET.get("well")
    if source:
        result = profile_for_well_source(source)
        if result[0] is not None:
            return result
    try:
        set_index = int(request.GET.get("set", "1"))
    except ValueError:
        set_index = 1
    return profile_for_well_index(set_index)


def fluxolot_context(request):
    source = request.GET.get("source") or request.GET.get("tank")
    if source:
        result = profile_for_fluxolot_source(source)
        if result[0] is not None:
            return result
    try:
        set_index = int(request.GET.get("set", "1"))
    except ValueError:
        set_index = 1
    return profile_for_fluxolot_index(set_index)


def profile_for_fluxolot_index(set_index: int):
    tanks = list(FLUXOLOT_TANKS)
    tank_count = len(tanks)
    if tank_count == 0:
        return None, None, 0, 1
    bounded_index = ((set_index - 1) % tank_count) + 1
    tank = tanks[bounded_index - 1]
    profile = TraceProfile.objects.filter(key=fluxolot_trace_profile_key(tank), enabled=True).first()
    return profile, NavigationOption(value=tank.key, label=tank.display_name), tank_count, bounded_index


def profile_for_fluxolot_source(source: str):
    tank_count = len(FLUXOLOT_TANKS)
    normalized = source.removeprefix(f"{FLUXOLOT_TRACE_SCOPE}-").removeprefix("fluxolot-").lower()
    for index, tank in enumerate(FLUXOLOT_TANKS, start=1):
        if normalized in {tank.key, tank.endpoint_name.lower(), fluxolot_trace_profile_key(tank)}:
            profile = TraceProfile.objects.filter(key=fluxolot_trace_profile_key(tank), enabled=True).first()
            return profile, NavigationOption(value=tank.key, label=tank.display_name), tank_count, index
    return None, None, tank_count, 1


def fluxolot_source_options() -> list[dict[str, str | int]]:
    return [
        {
            "value": tank.key,
            "label": tank.display_name,
            "set_index": index,
        }
        for index, tank in enumerate(FLUXOLOT_TANKS, start=1)
    ]


def fluxolot_chart(profile, *, tank, set_index: int, window_minutes: int | None = None, step_minutes: int = 1):
    if profile is None:
        return {
            "x": [],
            "series": [],
            "axisGroups": [],
            "windowDays": 1,
            "windowLabel": "1 day",
            "source": "trace-cache",
            "setIndex": set_index,
            "setLabel": "No Fluxolot Tanks",
        }
    payload_json = postgres_trace_payload_json(
        profile_id=profile.id,
        window_minutes=window_minutes or profile.cache_window_minutes,
        step_minutes=step_minutes,
        set_index=set_index,
        set_label=tank.label if tank else profile.label,
        well_id=tank.value if tank else "",
    )
    if payload_json is not None:
        return orjson.loads(payload_json)["traceChart"]
    payload = trace_cache_payload(profile, window_minutes=window_minutes, step_minutes=step_minutes)
    payload.update(
        {
            "setIndex": set_index,
            "setLabel": tank.label if tank else profile.label,
            "wellId": tank.value if tank else "",
        }
    )
    return payload


def profile_for_well_source(source: str):
    profiles = list(
        TraceProfile.objects.filter(
            key__startswith=f"{WELL_TRACE_PROFILE_PREFIX}-",
            enabled=True,
        ).order_by("id")
    )
    profile_count = len(profiles)
    source_key = (
        source
        if source.startswith(f"{WELL_TRACE_PROFILE_PREFIX}-")
        else f"{WELL_TRACE_PROFILE_PREFIX}-{source}"
    )
    for index, profile in enumerate(profiles, start=1):
        if profile.key == source_key:
            well_id = profile.key.removeprefix(f"{WELL_TRACE_PROFILE_PREFIX}-")
            return profile, NavigationOption(value=well_id, label=profile.label), profile_count, index
    return None, None, profile_count, 1


def nav_well_source_options() -> list[dict[str, str | int]]:
    profiles = TraceProfile.objects.filter(
        key__startswith=f"{WELL_TRACE_PROFILE_PREFIX}-",
        enabled=True,
    ).order_by("id")
    return [
        {
            "value": profile.key.removeprefix(f"{WELL_TRACE_PROFILE_PREFIX}-"),
            "label": profile.label,
            "set_index": index,
        }
        for index, profile in enumerate(profiles, start=1)
    ]


def trace_embed_mode(request) -> bool:
    return request.GET.get("embed") in {"1", "true", "yes"} or request.resolver_match.url_name == "nav-well-trace-embed"


def trace_link_context(request, trace_chart: dict, *, title: str) -> dict[str, dict[str, str]]:
    series = trace_chart.get("series") or []
    rows = [
        ("Title", title),
        ("Source", trace_chart.get("source", "runtime-samples")),
        ("Series count", len(series)),
        ("Window", trace_chart.get("windowLabel", "-")),
        ("Latest read", trace_chart.get("latestReadAt", "-")),
    ]
    link = flux_link(
        title="Flux Trace Chart",
        description="Flux Trace context describes the current chart source, window, visible series, and local cache/historian boundary.",
        rows=rows,
        payload={"type": "flux.trace.chart.context", "profile_key": trace_chart.get("profileKey"), "series_count": len(series)},
        docs_path="apps/trace/",
        page_url=request.build_absolute_uri(),
    )
    return {"trace_page_link": link, "trace_chart_link": link}


def trace_window_minutes(request, profile) -> int:
    default = profile.cache_window_minutes if profile else 1440
    try:
        requested = int(request.GET.get("window_minutes", default))
    except ValueError:
        return default
    return max(60, min(requested, trace_window_max_minutes(profile)))


def trace_window_max_minutes(profile) -> int:
    return max(10080, profile.cache_window_minutes if profile else 1440)


def trace_step_minutes(request, window_minutes: int) -> int:
    try:
        requested = int(request.GET.get("step_minutes", 0))
    except ValueError:
        requested = 0
    if requested > 0:
        return max(1, min(requested, 1440))
    if window_minutes >= 365 * 1440:
        return 60
    if window_minutes >= 30 * 1440:
        return 15
    return 7 if window_minutes >= 10080 else 1


def nav_well_chart(profile, *, well, set_index: int, window_minutes: int | None = None, step_minutes: int = 1):
    if profile is None:
        return {
            "x": [],
            "series": [],
            "axisGroups": [],
            "windowDays": 1,
            "windowLabel": "1 day",
            "source": "questdb-trace-cache",
            "setIndex": set_index,
            "setLabel": "No Wells",
        }
    payload_json = questdb_trace_payload_json(
        profile_id=profile.id,
        window_minutes=window_minutes or profile.cache_window_minutes,
        step_minutes=step_minutes,
        set_index=set_index,
        set_label=well.label if well else profile.label,
        well_id=well.value if well else "",
    )
    if payload_json is None:
        return empty_nav_well_chart(profile, well=well, set_index=set_index)
    return orjson.loads(payload_json)["traceChart"]


def empty_nav_well_chart(profile, *, well, set_index: int):
    signals = list(profile.signals.select_related("tag").filter(default_visible=True).order_by("sort_order", "id"))
    return {
        "x": [],
        "series": [empty_signal_payload(signal) for signal in signals],
        "axisGroups": nav_axis_groups(signals),
        "windowDays": 1,
        "windowLabel": "1 day",
        "source": "questdb-trace-cache",
        "profileKey": profile.key,
        "profileLabel": profile.label,
        "setIndex": set_index,
        "setLabel": well.label if well else profile.label,
        "wellId": well.value if well else "",
    }


def empty_signal_payload(signal):
    return {
        "rawCount": 0,
        "tagId": signal.tag_id,
        "signalId": signal.id,
        "name": signal.display_label,
        "fullPath": signal.tag.full_path,
        "unit": signal.display_unit,
        "axisKey": signal.axis_key,
        "x": [],
        "y": [],
    }


def nav_axis_groups(signals):
    groups = {}
    for index, signal in enumerate(signals, start=1):
        groups.setdefault(
            signal.axis_key,
            {
                "key": signal.axis_key,
                "label": signal.axis_label or signal.axis_key.replace("-", " ").title(),
                "unit": signal.axis_unit or signal.display_unit,
                "range": [signal.range_min, signal.range_max] if signal.range_min is not None and signal.range_max is not None else None,
                "side": 1 if index == 1 else 3,
            },
        )
    return list(groups.values())


def live(request):
    trace_chart = trace_sample_series(samples_per_tag=120)
    return render(
        request,
        "trace/live.html",
        {
            "trace_chart": trace_chart,
            "poll_seconds": 5,
            "window_minutes": 15,
            **trace_link_context(request, trace_chart, title="Live Tag Trace"),
        },
    )


def live_samples(request):
    since = parse_datetime(request.GET.get("since", ""))
    return JsonResponse(trace_sample_series(samples_per_tag=120, since=since))
