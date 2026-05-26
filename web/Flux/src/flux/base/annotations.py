from __future__ import annotations

import json
from dataclasses import dataclass

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from flux.trace.models import TraceAnnotation, TraceAnnotationTarget, TraceProfile, TraceSignal


@dataclass(frozen=True)
class AnnotationTargetWrite:
    historian_path: str
    ignition_storage_id: str
    quality_code: str = ""


def trace_annotation_profile(profile_key: str) -> TraceProfile | None:
    return TraceProfile.objects.filter(key=profile_key or "").first()


def create_trace_annotation(
    *,
    profile: TraceProfile | None,
    marker_id,
    marker_time,
    text: str,
    targets: list[AnnotationTargetWrite],
) -> TraceAnnotation:
    signals_by_path = trace_signals_by_path()
    annotation = TraceAnnotation.objects.create(
        profile=profile,
        marker_id=marker_id,
        marker_time=marker_time,
        text=text,
    )
    TraceAnnotationTarget.objects.bulk_create(
        [
            TraceAnnotationTarget(
                annotation=annotation,
                signal=signals_by_path.get(target.historian_path),
                historian_path=target.historian_path,
                ignition_storage_id=target.ignition_storage_id,
                quality_code=target.quality_code,
            )
            for target in targets
        ]
    )
    return annotation


def update_trace_annotation_target_qualities(annotation: TraceAnnotation, qualities: list[str]) -> None:
    if not qualities:
        return
    targets = list(annotation.targets.order_by("id"))
    for index, target in enumerate(targets):
        if index >= len(qualities):
            break
        target.quality_code = str(qualities[index])
    TraceAnnotationTarget.objects.bulk_update(targets, ["quality_code"])


def local_trace_annotations(*, profile, paths: list[str], start_time: int, end_time: int) -> list[dict]:
    start_dt = timezone.datetime.fromtimestamp(start_time / 1000, tz=timezone.get_current_timezone())
    end_dt = timezone.datetime.fromtimestamp(end_time / 1000, tz=timezone.get_current_timezone())
    annotations = (
        TraceAnnotation.objects.prefetch_related("targets")
        .filter(profile=profile, marker_time__gte=start_dt, marker_time__lte=end_dt, targets__historian_path__in=paths)
        .distinct()
        .order_by("marker_time", "id")
    )
    return [
        {
            "id": str(annotation.id),
            "localId": annotation.id,
            "markerId": annotation.marker_id,
            "sequence": index + 1,
            "pinnedAt": annotation.marker_time.isoformat(),
            "text": annotation.text,
            "saved": True,
            "storageIds": [str(target.ignition_storage_id) for target in annotation.targets.all()],
        }
        for index, annotation in enumerate(annotations)
    ]


def recover_ignition_trace_annotations(profile, ignition_annotations) -> list[dict]:
    signals_by_path = trace_signals_by_path()
    storage_ids = [annotation.storage_id for annotation in ignition_annotations if annotation.storage_id]
    existing_targets = {
        str(target.ignition_storage_id): target
        for target in TraceAnnotationTarget.objects.select_related("annotation").filter(ignition_storage_id__in=storage_ids)
    }
    groups = {}
    for ignition_annotation in ignition_annotations:
        try:
            data = json.loads(ignition_annotation.data or "{}")
        except json.JSONDecodeError:
            data = {}
        if data.get("source") != "flux.trace":
            continue
        annotation_key = data.get("id") or ignition_annotation.storage_id
        groups.setdefault(annotation_key, {"data": data, "items": []})["items"].append(ignition_annotation)
    recovered = []
    for annotation_key, group in groups.items():
        data = group["data"]
        text = str(data.get("text") or "").strip()
        pinned_at = str(data.get("pinnedAt") or "")
        if not text or not pinned_at:
            continue
        marker_time = parse_datetime(pinned_at) or timezone.now()
        existing = next((existing_targets.get(item.storage_id) for item in group["items"] if item.storage_id in existing_targets), None)
        annotation = existing.annotation if existing else TraceAnnotation.objects.create(
            profile=profile,
            marker_id=data.get("markerId"),
            marker_time=marker_time,
            text=text,
        )
        for item in group["items"]:
            if not item.storage_id or item.storage_id in existing_targets:
                continue
            TraceAnnotationTarget.objects.create(
                annotation=annotation,
                signal=signals_by_path.get(item.path),
                historian_path=item.path,
                ignition_storage_id=item.storage_id,
                quality_code="Recovered",
            )
        recovered.append(
            {
                "id": annotation_key,
                "localId": annotation.id,
                "markerId": data.get("markerId"),
                "sequence": data.get("sequence"),
                "pinnedAt": pinned_at,
                "text": text,
                "saved": True,
                "storageIds": [item.storage_id for item in group["items"] if item.storage_id],
            }
        )
    return recovered


def trace_signals_by_path() -> dict[str, TraceSignal]:
    signals = {}
    for signal in TraceSignal.objects.select_related("tag", "series", "series__base_tag"):
        signals[signal.tag.full_path] = signal
        signals[signal.chart_full_path] = signal
    return signals
