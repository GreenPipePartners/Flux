from __future__ import annotations

import orjson
from dataclasses import dataclass

from flux.chart.cache import plane_sample_payload
from flux.chart.data_plane import postgres_trace_payload_json
from flux.opt.services import touch_runtime_demand
from flux.sim.fluxolot_fishtank import FLUXOLOT_TANKS, FLUXOLOT_TRACE_SCOPE, fluxolot_trace_profile_key
from flux.trace.models import TraceProfile


@dataclass(frozen=True)
class ChartSource:
    value: str
    label: str


RESERVED_CHART_PROFILE_PATHS = {"annotations", "cache", "fluxolot", "live", "stream"}
TRACE_DEMAND_TTL_SECONDS = 180


def profile_trace_chart(profile: TraceProfile, *, window_minutes: int | None = None, step_minutes: int = 1) -> dict:
    return plane_sample_payload(profile, window_minutes=window_minutes, step_minutes=step_minutes)


def profile_payload_json(profile: TraceProfile, *, window_minutes: int, step_minutes: int = 1) -> bytes | None:
    return postgres_trace_payload_json(
        profile_id=profile.id,
        window_minutes=window_minutes,
        step_minutes=step_minutes,
    )


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
    return profile, ChartSource(value=tank.key, label=tank.display_name), tank_count, bounded_index


def profile_for_fluxolot_source(source: str):
    tank_count = len(FLUXOLOT_TANKS)
    normalized = source.removeprefix(f"{FLUXOLOT_TRACE_SCOPE}-").removeprefix("fluxolot-").lower()
    for index, tank in enumerate(FLUXOLOT_TANKS, start=1):
        if normalized in {tank.key, tank.endpoint_name.lower(), fluxolot_trace_profile_key(tank)}:
            profile = TraceProfile.objects.filter(key=fluxolot_trace_profile_key(tank), enabled=True).first()
            return profile, ChartSource(value=tank.key, label=tank.display_name), tank_count, index
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


def fluxolot_payload_json(profile, *, tank, set_index: int, window_minutes: int, step_minutes: int) -> bytes | None:
    if profile is None:
        return None
    return postgres_trace_payload_json(
        profile_id=profile.id,
        window_minutes=window_minutes,
        step_minutes=step_minutes,
        set_index=set_index,
        set_label=tank.label if tank else profile.label,
        well_id=tank.value if tank else "",
    )


def fluxolot_chart(profile, *, tank, set_index: int, window_minutes: int | None = None, step_minutes: int = 1):
    if profile is None:
        return {
            "x": [],
            "series": [],
            "axisGroups": [],
            "windowDays": 1,
            "windowLabel": "1 day",
            "source": "plane-samples",
            "setIndex": set_index,
            "setLabel": "No Fluxolot Tanks",
        }
    payload_json = fluxolot_payload_json(
        profile,
        tank=tank,
        set_index=set_index,
        window_minutes=window_minutes or profile.cache_window_minutes,
        step_minutes=step_minutes,
    )
    if payload_json is not None:
        return orjson.loads(payload_json)["traceChart"]
    payload = profile_trace_chart(profile, window_minutes=window_minutes, step_minutes=step_minutes)
    payload.update(
        {
            "setIndex": set_index,
            "setLabel": tank.label if tank else profile.label,
            "wellId": tank.value if tank else "",
        }
    )
    return payload


def trace_embed_mode(request) -> bool:
    return request.GET.get("embed") in {"1", "true", "yes"}


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


def touch_trace_profile_demand(profile) -> int:
    if profile is None:
        return 0
    return touch_runtime_demand(
        source_key=f"trace-profile:{profile.key}",
        tags=(signal.tag for signal in profile.signals.select_related("tag").filter(tag__enabled=True)),
        seconds=TRACE_DEMAND_TTL_SECONDS,
        claimed_by="flux-trace-ui",
        metadata={"profile_key": profile.key},
    )
