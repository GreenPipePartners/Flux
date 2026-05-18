import json

import orjson
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.dateparse import parse_datetime

from flux.base.runtime import TagSample
from flux.trace.models import TraceProfile
from trace.annotations import TraceAnnotationError, query_saved_annotations, store_annotation
from trace.cache import trace_cache_payload
from trace.data_plane import postgres_trace_payload_json
from trace.providers.nav_wells import profile_for_well_index
from trace.questdb_data_plane import questdb_trace_payload_json

from .selectors import trace_sample_series


@ensure_csrf_cookie
def index(request):
    samples = TagSample.objects.select_related("tag").order_by("-read_at")[:50]
    return render(
        request,
        "trace/index.html",
        {
            "samples": samples,
            "trace_chart": trace_sample_series(),
        },
    )


@ensure_csrf_cookie
def cache_profile(request, profile_key: str):
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
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
        },
    )


def cache_profile_payload(request, profile_key: str):
    profile = get_object_or_404(TraceProfile, key=profile_key, enabled=True)
    payload_json = postgres_trace_payload_json(profile_id=profile.id, window_minutes=profile.cache_window_minutes)
    if payload_json is not None:
        return HttpResponse(payload_json, content_type="application/json")
    return trace_json_response({"traceChart": trace_cache_payload(profile), "traceError": ""})


@ensure_csrf_cookie
def nav_well_trace(request):
    profile, well, well_count, set_index = nav_well_context(request)
    window_minutes = trace_window_minutes(request, profile)
    step_minutes = trace_step_minutes(request, window_minutes)
    trace_chart = nav_well_chart(profile, well=well, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes)
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
            "trace_live_refresh_seconds": 60,
            "trace_help": "Click inside the chart to pin a vertical trace cursor. Drag selects an x-range to zoom. Shift-drag pans. Wheel zooms; side-scroll pans. Use Previous/Next Well or left/right arrow keys to cycle wells.",
        },
    )


def nav_well_trace_payload(request):
    profile, well, _well_count, set_index = nav_well_context(request)
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
    return trace_json_response({"traceChart": nav_well_chart(profile, well=well, set_index=set_index, window_minutes=window_minutes, step_minutes=step_minutes), "traceError": "" if profile else "No navigation well trace profiles seeded yet."})


def trace_json_response(payload: dict) -> HttpResponse:
    return JsonResponse(payload)


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
    try:
        set_index = int(request.GET.get("set", "1"))
    except ValueError:
        set_index = 1
    return profile_for_well_index(set_index)


def trace_window_minutes(request, profile) -> int:
    default = profile.cache_window_minutes if profile else 1440
    try:
        requested = int(request.GET.get("window_minutes", default))
    except ValueError:
        return default
    return max(60, min(requested, 10080))


def trace_step_minutes(request, window_minutes: int) -> int:
    try:
        requested = int(request.GET.get("step_minutes", 0))
    except ValueError:
        requested = 0
    if requested > 0:
        return max(1, min(requested, 60))
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
    return render(
        request,
        "trace/live.html",
        {
            "trace_chart": trace_sample_series(samples_per_tag=120),
            "poll_seconds": 5,
            "window_minutes": 15,
        },
    )


def live_samples(request):
    since = parse_datetime(request.GET.get("since", ""))
    return JsonResponse(trace_sample_series(samples_per_tag=120, since=since))
