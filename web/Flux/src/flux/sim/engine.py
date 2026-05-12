from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from django.db import transaction
from django.utils import timezone

from .models import SimHistoryBackfill, SimTag


class FluxyLike(Protocol):
    tag: Any
    historian: Any


@dataclass(frozen=True)
class SimulatedValue:
    tag: SimTag
    value: Any


def tag_config(tag: SimTag) -> dict[str, Any]:
    return {
        "name": tag.name,
        "tagType": "AtomicTag",
        "valueSource": "memory",
        "dataType": tag.data_type,
        "value": value_for_tag(tag, 0),
    }


def value_for_tag(tag: SimTag, sample_index: int) -> Any:
    if tag.pattern == SimTag.Pattern.BOOL_TOGGLE:
        return bool((sample_index // max(tag.period_samples, 1)) % 2)
    if tag.pattern == SimTag.Pattern.INT_RAMP:
        return int(tag.baseline + (sample_index * tag.step))
    if tag.pattern == SimTag.Pattern.FLOAT_WAVE:
        radians = (2.0 * math.pi * sample_index) / max(tag.period_samples, 1)
        return tag.baseline + (tag.amplitude * math.sin(radians))
    raise ValueError("Unsupported sim pattern: %s" % tag.pattern)


def configure_enabled_tags(fx: FluxyLike) -> Any:
    tags_by_base_path: dict[str, list[SimTag]] = {}
    for tag in SimTag.objects.filter(enabled=True).select_related("schedule"):
        base_path = f"[{tag.provider}]"
        tags_by_base_path.setdefault(base_path, []).append(tag)

    results = []
    for base_path, tags in tags_by_base_path.items():
        folders: dict[str, list[dict[str, Any]]] = {}
        for tag in tags:
            folders.setdefault(tag.folder_path.strip("/"), []).append(tag_config(tag))
        for folder_path, configs in folders.items():
            parts = folder_path.split("/")
            folder_name = parts[-1]
            parent_path = base_path if len(parts) == 1 else base_path + "/" + "/".join(parts[:-1])
            results.extend(
                fx.tag.configure(
                    [{"name": folder_name, "tagType": "Folder", "tags": configs}],
                    base_path=parent_path,
                    collision_policy="o",
                )
            )
    return results


def write_due_tags(fx: FluxyLike, *, now=None, batch_size: int = 500) -> int:
    now = now or timezone.now()
    due_tags = list(
        SimTag.objects.select_related("schedule")
        .filter(enabled=True, schedule__enabled=True, next_write_at__lte=now)
        .order_by("next_write_at", "id")[:batch_size]
    )
    if not due_tags:
        return 0

    values = [value_for_tag(tag, tag.sample_index) for tag in due_tags]
    fx.tag.write_blocking([tag.tag_path for tag in due_tags], values)

    with transaction.atomic():
        for tag, value in zip(due_tags, values, strict=True):
            tag.last_value = value
            tag.last_write_at = now
            tag.next_write_at = now + timedelta(seconds=tag.schedule.interval_seconds)
            tag.sample_index += 1
            tag.save(
                update_fields=[
                    "last_value",
                    "last_write_at",
                    "next_write_at",
                    "sample_index",
                ]
            )
    return len(due_tags)


def run_history_backfill(fx: FluxyLike, backfill: SimHistoryBackfill) -> int:
    tags = list(SimTag.objects.filter(enabled=True, history_enabled=True).select_related("schedule"))
    if not tags:
        return 0

    backfill.status = SimHistoryBackfill.Status.RUNNING
    backfill.last_error = ""
    backfill.save(update_fields=["status", "last_error"])

    try:
        start = backfill.start_at
        end = start + timedelta(days=backfill.duration_days)
        interval = timedelta(seconds=backfill.interval_seconds)
        timestamp = start
        sample_index = 0
        written = 0
        paths: list[str] = []
        values: list[Any] = []
        timestamps: list[int] = []
        qualities: list[int] = []

        while timestamp <= end:
            timestamp_ms = int(timestamp.timestamp() * 1000)
            for tag in tags:
                paths.append(backfill.history_prefix.rstrip("/") + "/" + tag.folder_path.strip("/") + "/" + tag.name)
                values.append(value_for_tag(tag, sample_index))
                timestamps.append(timestamp_ms)
                qualities.append(192)
                if len(paths) >= backfill.chunk_size:
                    fx.historian.store_data_points(paths, values, timestamps=timestamps, qualities=qualities)
                    written += len(paths)
                    paths, values, timestamps, qualities = [], [], [], []
            sample_index += 1
            timestamp += interval

        if paths:
            fx.historian.store_data_points(paths, values, timestamps=timestamps, qualities=qualities)
            written += len(paths)

        backfill.status = SimHistoryBackfill.Status.COMPLETED
        backfill.completed_at = timezone.now()
        backfill.save(update_fields=["status", "completed_at"])
        return written
    except Exception as exc:
        backfill.status = SimHistoryBackfill.Status.FAILED
        backfill.last_error = str(exc)
        backfill.save(update_fields=["status", "last_error"])
        raise
