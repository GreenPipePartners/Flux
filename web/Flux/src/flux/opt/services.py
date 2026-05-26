from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.db.models import Q
from django.utils import timezone

from flux.base.runtime import LatestTagValue, RuntimeSchedulerConfig, RuntimeTag, TagSample
from flux.plane.services import RuntimePlaneSample, mirror_runtime_samples_to_plane
from flux.sim.demo import parse_fluxy_timestamp

from .models import OptimizationLease, RefreshLane, RuntimeDemand


HISTORY_CONFIGURATION_FIELDS = (
    "historyEnabled",
    "historyProvider",
    "historySampleMode",
    "historySampleRate",
    "historySampleRateUnits",
    "historyMinTimeBetweenSamples",
    "historyMinTimeUnits",
    "historicalDeadband",
    "historicalDeadbandMode",
    "historyMaxAge",
    "historyMaxAgeUnits",
)


REFRESH_LANES = {
    "hot": {
        "interval_seconds": 10,
        "priority": 10,
        "max_batch_size": 100,
        "max_runtime_ms": 3_000,
        "enabled": True,
    },
    "warm": {
        "interval_seconds": 30,
        "priority": 30,
        "max_batch_size": 250,
        "max_runtime_ms": 5_000,
        "enabled": True,
    },
    "cold": {
        "interval_seconds": 60,
        "priority": 60,
        "max_batch_size": 500,
        "max_runtime_ms": 8_000,
        "enabled": True,
    },
}


@dataclass(frozen=True)
class HistoryMetadataReport:
    attempted: bool = False
    supported: bool = False
    full_path_count: int = 0
    fields: tuple[str, ...] = HISTORY_CONFIGURATION_FIELDS
    tags: tuple[dict[str, Any], ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class DemandSamplingReport:
    sampled_count: int
    leased_count: int
    full_paths: tuple[str, ...]
    history: HistoryMetadataReport = field(default_factory=HistoryMetadataReport)


def normalize_refresh_lanes() -> int:
    normalized = 0
    for name, defaults in REFRESH_LANES.items():
        _lane, created = RefreshLane.objects.update_or_create(name=name, defaults=defaults)
        normalized += int(created)
    return normalized


def fluxy_client():
    import fluxy

    return fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN") or None,
    )


def due_runtime_tags(*, now=None, limit: int | None = None) -> list[RuntimeTag]:
    now = now or timezone.now()
    demand_paths = active_demand_full_paths(now=now)
    demand_keys = {parse_full_tag_path(full_path) for full_path in demand_paths}
    config = RuntimeSchedulerConfig.default()
    candidates = (
        RuntimeTag.objects.select_related("latest_value", "schedule")
        .filter(enabled=True, schedule__enabled=True)
        .filter(Q(latest_value__isnull=True) | Q(schedule__interval_seconds__gt=0))
        .order_by("latest_value__read_at", "asset_name", "display_name", "id")
    )
    demand_due: list[RuntimeTag] = []
    regular_due: list[RuntimeTag] = []
    for tag in candidates:
        latest = getattr(tag, "latest_value", None)
        interval_seconds = tag.schedule.interval_seconds
        is_demand = (tag.provider, tag.path) in demand_keys
        if is_demand:
            interval_seconds = min(interval_seconds, config.hot_interval_seconds)
        if latest is None or (now - latest.read_at).total_seconds() >= interval_seconds:
            if is_demand:
                demand_due.append(tag)
            else:
                regular_due.append(tag)
    due = demand_due + regular_due
    if limit is not None:
        return due[:limit]
    return due


def sample_runtime_tags(tags: Iterable[RuntimeTag], *, fx: Any | None = None, now=None) -> int:
    runtime_tags = list(tags)
    if not runtime_tags:
        return 0
    fx = fx or fluxy_client()
    values = fx.tag.read_blocking([tag.full_path for tag in runtime_tags])
    read_at = now or timezone.now()
    samples = []
    plane_samples = []
    for tag, value in zip(runtime_tags, values, strict=True):
        value_timestamp = parse_fluxy_timestamp(value.timestamp) or read_at
        LatestTagValue.objects.update_or_create(
            tag=tag,
            defaults={
                "value": value.value,
                "quality_code": value.quality,
                "value_timestamp": value_timestamp,
                "read_at": read_at,
            },
        )
        samples.append(
            TagSample(
                tag=tag,
                value=value.value,
                quality_code=value.quality,
                value_timestamp=value_timestamp,
                read_at=read_at,
            )
        )
        plane_samples.append(
            RuntimePlaneSample(
                tag=tag,
                value=value.value,
                quality_code=value.quality,
                value_timestamp=value_timestamp,
                read_at=read_at,
            )
        )
    TagSample.objects.bulk_create(samples)
    mirror_runtime_samples_to_plane(plane_samples, now=read_at)
    return len(runtime_tags)


def sample_runtime_tag_paths(full_paths: Iterable[str], *, fx: Any | None = None, now=None) -> int:
    runtime_tags = runtime_tags_for_full_paths(full_paths)
    return sample_runtime_tags(runtime_tags, fx=fx, now=now)


def sample_runtime_demand(
    *,
    tags: Iterable[RuntimeTag] | None = None,
    full_paths: Iterable[str] | None = None,
    lease_seconds: int | None = None,
    fx: Any | None = None,
    now=None,
) -> DemandSamplingReport:
    runtime_tags = list(tags or [])
    if full_paths is not None:
        runtime_tags.extend(runtime_tags_for_full_paths(full_paths))
    unique_tags = list({tag.full_path: tag for tag in runtime_tags}.values())
    leased_count = lease_runtime_tags_hot(unique_tags, seconds=lease_seconds, now=now)
    sampled_count = sample_runtime_tags(unique_tags, fx=fx, now=now)
    full_path_tuple = tuple(tag.full_path for tag in unique_tags)
    return DemandSamplingReport(
        sampled_count=sampled_count,
        leased_count=leased_count,
        full_paths=full_path_tuple,
        history=history_metadata_report(full_path_tuple, fx=fx),
    )


def lease_runtime_tags_hot(
    tags: Iterable[RuntimeTag], *, seconds: int | None = None, claimed_by: str = "flux-demand", now=None
) -> int:
    runtime_tags = list(tags)
    if not runtime_tags:
        return 0
    now = now or timezone.now()
    seconds = seconds if seconds is not None else RuntimeSchedulerConfig.default().demand_lease_seconds
    expires_at = now + timezone.timedelta(seconds=max(seconds, 1))
    full_paths = [tag.full_path for tag in runtime_tags]
    OptimizationLease.objects.filter(
        work_type="runtime_tag_demand",
        target_path__in=full_paths,
        completed_at__isnull=True,
    ).update(completed_at=now)
    OptimizationLease.objects.bulk_create(
        [
            OptimizationLease(
                work_type="runtime_tag_demand",
                target_path=full_path,
                claimed_by=claimed_by,
                claimed_at=now,
                expires_at=expires_at,
            )
            for full_path in full_paths
        ]
    )
    return len(full_paths)


def lease_runtime_demand(
    *,
    tags: Iterable[RuntimeTag] | None = None,
    full_paths: Iterable[str] | None = None,
    seconds: int | None = None,
    claimed_by: str = "flux-demand-ui",
    now=None,
) -> int:
    runtime_tags = list(tags or [])
    if full_paths is not None:
        runtime_tags.extend(runtime_tags_for_full_paths(full_paths))
    unique_tags = list({tag.full_path: tag for tag in runtime_tags}.values())
    return lease_runtime_tags_hot(unique_tags, seconds=seconds, claimed_by=claimed_by, now=now)


def touch_runtime_demand(
    *,
    source_key: str,
    tags: Iterable[RuntimeTag] | None = None,
    full_paths: Iterable[str] | None = None,
    seconds: int | None = None,
    claimed_by: str = "flux-demand-ui",
    metadata: dict[str, Any] | None = None,
    now=None,
) -> int:
    runtime_tags = list(tags or [])
    if full_paths is not None:
        runtime_tags.extend(runtime_tags_for_full_paths(full_paths))
    unique_paths = tuple(dict.fromkeys(tag.full_path for tag in runtime_tags))
    if not unique_paths:
        return 0
    now = now or timezone.now()
    seconds = seconds if seconds is not None else RuntimeSchedulerConfig.default().demand_lease_seconds
    expires_at = now + timezone.timedelta(seconds=max(seconds, 1))
    demand_metadata = metadata or {}
    existing_paths = set(
        RuntimeDemand.objects.filter(source_key=source_key, target_path__in=unique_paths).values_list(
            "target_path", flat=True
        )
    )
    RuntimeDemand.objects.filter(source_key=source_key, target_path__in=existing_paths).update(
        claimed_by=claimed_by,
        touched_at=now,
        expires_at=expires_at,
        metadata=demand_metadata,
    )
    RuntimeDemand.objects.bulk_create(
        [
            RuntimeDemand(
                source_key=source_key,
                target_path=full_path,
                claimed_by=claimed_by,
                touched_at=now,
                expires_at=expires_at,
                metadata=demand_metadata,
            )
            for full_path in unique_paths
            if full_path not in existing_paths
        ]
    )
    return len(unique_paths)


def active_demand_full_paths(*, now=None) -> set[str]:
    now = now or timezone.now()
    lease_paths = set(
        OptimizationLease.objects.filter(
            work_type="runtime_tag_demand",
            completed_at__isnull=True,
            expires_at__gt=now,
        ).values_list("target_path", flat=True)
    )
    demand_paths = set(
        RuntimeDemand.objects.filter(expires_at__gt=now).values_list("target_path", flat=True)
    )
    return lease_paths | demand_paths


def runtime_tags_for_full_paths(full_paths: Iterable[str]) -> list[RuntimeTag]:
    keys = [parse_full_tag_path(full_path) for full_path in full_paths]
    if not keys:
        return []
    query = Q()
    for provider, path in keys:
        query |= Q(provider=provider, path=path)
    tags_by_path = {
        tag.full_path: tag
        for tag in RuntimeTag.objects.select_related("schedule").filter(query, enabled=True)
    }
    return [
        tags_by_path[format_full_tag_path(provider, path)]
        for provider, path in keys
        if format_full_tag_path(provider, path) in tags_by_path
    ]


def runtime_tags_for_prefix(
    *,
    provider: str,
    path_prefix: str,
    category: str = "",
    limit: int | None = None,
) -> list[RuntimeTag]:
    query = RuntimeTag.objects.select_related("latest_value", "schedule").filter(
        provider=provider,
        path__startswith=path_prefix,
        enabled=True,
        schedule__enabled=True,
    )
    if category:
        query = query.filter(category=category)
    query = query.order_by("asset_name", "display_name", "id")
    if limit is not None:
        query = query[:limit]
    return list(query)


def parse_full_tag_path(full_path: str) -> tuple[str, str]:
    if not full_path.startswith("[") or "]" not in full_path:
        raise ValueError("Runtime tag full paths must use the [provider]path format")
    provider, path = full_path[1:].split("]", 1)
    if not provider or not path:
        raise ValueError("Runtime tag full paths must include provider and path")
    return provider, path


def format_full_tag_path(provider: str, path: str) -> str:
    return f"[{provider}]{path}"


def history_metadata_report(full_paths: Iterable[str], *, fx: Any | None = None) -> HistoryMetadataReport:
    full_path_tuple = tuple(dict.fromkeys(full_paths))
    if not full_path_tuple:
        return HistoryMetadataReport(full_path_count=0)
    fx = fx or fluxy_client()
    tag_client = getattr(fx, "tag", None)
    get_configuration = getattr(tag_client, "get_configuration", None)
    if get_configuration is None:
        return HistoryMetadataReport(
            attempted=True,
            supported=False,
            full_path_count=len(full_path_tuple),
            error="fx.tag.get_configuration is not available",
        )

    try:
        configs = get_configuration(list(full_path_tuple), recursive=False)
    except Exception as batch_exc:
        try:
            configs = []
            for full_path in full_path_tuple:
                for config in get_configuration(full_path, recursive=False):
                    if isinstance(config, dict) and "fullPath" not in config:
                        config = {**config, "fullPath": full_path}
                    configs.append(config)
        except Exception as loop_exc:
            return HistoryMetadataReport(
                attempted=True,
                supported=False,
                full_path_count=len(full_path_tuple),
                error=f"{type(loop_exc).__name__}: {loop_exc}; batch fallback after {type(batch_exc).__name__}: {batch_exc}",
            )

    tags = tuple(_history_metadata_from_config(config) for config in configs if isinstance(config, dict))
    return HistoryMetadataReport(
        attempted=True,
        supported=True,
        full_path_count=len(full_path_tuple),
        tags=tags,
    )


def _history_metadata_from_config(config: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        field: config[field]
        for field in HISTORY_CONFIGURATION_FIELDS
        if field in config
    }
    full_path = config.get("fullPath") or config.get("full_path")
    if full_path is not None:
        metadata = {"fullPath": full_path, **metadata}
    elif config.get("name") is not None:
        metadata = {"name": config["name"], **metadata}
    return metadata


def sample_due_runtime_tags(*, fx: Any | None = None, limit: int | None = None, now=None) -> int:
    normalize_refresh_lanes()
    read_at = now or timezone.now()
    return sample_runtime_tags(due_runtime_tags(now=read_at, limit=limit), fx=fx, now=read_at)
