from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from django.db import transaction
from django.utils import timezone
from flux_sim.tag_mode import TagModeConfig, value_to_write

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


def delete_configured_tags(fx: FluxyLike, *, provider: str, folder_path: str) -> int:
    return delete_tag_branch(fx, provider=provider, folder_path=folder_path)


def delete_tag_branch(fx: FluxyLike, *, provider: str, folder_path: str) -> int:
    folder_path = folder_path.strip("/")
    if not provider or not folder_path:
        raise ValueError("provider and folder_path are required to delete simulated tags")
    fx.tag.delete_tags([f"[{provider}]{folder_path}"])
    return 1


def deletion_targets(tags) -> list[str]:
    folder_paths_by_provider: dict[str, set[str]] = {}
    tag_paths: set[str] = set()
    for tag in tags:
        folder_path = tag.folder_path.strip("/")
        if folder_path:
            folder_paths_by_provider.setdefault(tag.provider, set()).add(folder_path)
        else:
            tag_paths.add(f"[{tag.provider}]{tag.name}")

    targets = set(tag_paths)
    for provider, folder_paths in folder_paths_by_provider.items():
        for folder_path in minimal_folder_paths(folder_paths):
            targets.add(f"[{provider}]{folder_path}")
    return sorted(targets)


def minimal_folder_paths(folder_paths: set[str]) -> list[str]:
    selected: list[str] = []
    for folder_path in sorted(folder_paths, key=lambda value: (value.count("/"), value)):
        if any(folder_path == parent or folder_path.startswith(parent + "/") for parent in selected):
            continue
        selected.append(folder_path)
    return selected


def write_due_tags(fx: FluxyLike, *, now=None, batch_size: int = 500) -> int:
    now = now or timezone.now()
    due_tags = list(
        SimTag.objects.select_related("schedule")
        .filter(enabled=True, schedule__enabled=True, next_write_at__lte=now)
        .order_by("next_write_at", "id")[:batch_size]
    )
    if not due_tags:
        return 0

    results = [behavior_result_for_tag(tag, value_for_tag(tag, tag.sample_index), now=now) for tag in due_tags]
    tag_paths = [tag.tag_path for tag in due_tags]
    primary_values = [result.value for result in results]
    values = list(primary_values)
    for result in results:
        for side_write in result.side_writes:
            tag_paths.append(side_write.tag_path)
            values.append(side_write.value)
    fx.tag.write_blocking(tag_paths, values)

    with transaction.atomic():
        for tag, value, result in zip(due_tags, primary_values, results, strict=True):
            tag.last_value = value
            tag.pending_value = result.pending_value
            tag.pending_apply_at = result.pending_apply_at
            tag.last_write_at = now
            tag.next_write_at = now + timedelta(seconds=tag.schedule.interval_seconds)
            tag.sample_index += 1
            tag.save(
                update_fields=[
                    "last_value",
                    "pending_value",
                    "pending_apply_at",
                    "last_write_at",
                    "next_write_at",
                    "sample_index",
                ]
            )
    return len(due_tags)


def behavior_result_for_tag(tag: SimTag, target_value: Any, *, now) -> Any:
    return value_to_write(
        target_value,
        now=now,
        config=TagModeConfig(
            kind=tag.behavior,
            response_delay_seconds=tag.response_delay_seconds,
            last_value=tag.last_value,
            pending_value=tag.pending_value,
            pending_apply_at=tag.pending_apply_at,
            mode_config=tag.mode_config or {},
        ),
    )


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
