from __future__ import annotations

import json
import os
import uuid

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from flux.trace.models import TraceAnnotation, TraceAnnotationTarget, TraceProfile, TraceSignal


class TraceAnnotationError(ValueError):
    pass


def store_annotation(payload: dict) -> dict:
    text = str(payload.get("text") or "").strip()
    pinned_at = str(payload.get("pinnedAt") or "")
    paths = payload.get("paths") or []
    if not text:
        raise TraceAnnotationError("Annotation text is required")
    if not pinned_at:
        raise TraceAnnotationError("pinnedAt is required")
    if not isinstance(paths, list) or not paths:
        raise TraceAnnotationError("At least one historian path is required")
    marker_time = parse_datetime(pinned_at)
    if marker_time is None:
        raise TraceAnnotationError("pinnedAt must be an ISO timestamp")
    profile = TraceProfile.objects.filter(key=payload.get("profileKey") or "").first()
    signals_by_path = {signal.tag.full_path: signal for signal in TraceSignal.objects.select_related("tag")}
    annotation_id = str(uuid.uuid4())
    storage_ids = [str(uuid.uuid4()) for _path in paths]
    qualities = store_ignition_annotations(
        paths=paths,
        marker_ms=int(marker_time.timestamp() * 1000),
        storage_ids=storage_ids,
        annotation_data=json.dumps(
            {
                "id": annotation_id,
                "markerId": payload.get("markerId"),
                "sequence": payload.get("sequence"),
                "pinnedAt": pinned_at,
                "text": text,
                "source": "flux.trace",
            },
            separators=(",", ":"),
        ),
    )
    annotation = TraceAnnotation.objects.create(
        profile=profile,
        marker_id=payload.get("markerId"),
        marker_time=marker_time,
        text=text,
    )
    TraceAnnotationTarget.objects.bulk_create(
        [
            TraceAnnotationTarget(
                annotation=annotation,
                signal=signals_by_path.get(path),
                historian_path=path,
                ignition_storage_id=storage_id,
                quality_code=str((qualities or [""] * len(paths))[index] if index < len(qualities or []) else ""),
            )
            for index, (path, storage_id) in enumerate(zip(paths, storage_ids, strict=True))
        ]
    )
    return {
        "annotation": {
            "id": annotation_id,
            "localId": annotation.id,
            "storageIds": storage_ids,
            "markerId": payload.get("markerId"),
            "sequence": payload.get("sequence"),
            "pinnedAt": pinned_at,
            "text": text,
        },
        "qualities": [str(quality) for quality in (qualities or [])],
    }


def store_ignition_annotations(*, paths: list[str], marker_ms: int, storage_ids: list[str], annotation_data: str):
    import fluxy

    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
    )
    return fx.historian.store_annotations(
        paths,
        [marker_ms] * len(paths),
        end_times=[marker_ms] * len(paths),
        types=["flux.trace.annotation"] * len(paths),
        data=[annotation_data] * len(paths),
        storage_ids=storage_ids,
    )


def query_saved_annotations(payload: dict) -> dict:
    paths = payload.get("paths") or []
    start_time = payload.get("startTime")
    end_time = payload.get("endTime")
    if not isinstance(paths, list) or not paths:
        raise TraceAnnotationError("At least one historian path is required")
    if start_time is None or end_time is None:
        raise TraceAnnotationError("startTime and endTime are required")
    profile = TraceProfile.objects.filter(key=payload.get("profileKey") or "").first()
    return {
        "annotations": local_annotations(profile=profile, paths=paths, start_time=int(start_time), end_time=int(end_time)),
        "warning": "",
    }


def query_ignition_annotations(*, paths: list[str], start_time: int, end_time: int):
    import fluxy

    fx = fluxy.Fluxy(
        base_url=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"),
        token=os.getenv("FLUXY_TOKEN"),
    )
    return fx.historian.query_annotations(paths, start_time, end_date=end_time)


def local_annotations(*, profile, paths: list[str], start_time: int, end_time: int) -> list[dict]:
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


def merge_annotations(*annotation_groups: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for group in annotation_groups:
        for annotation in group:
            key = annotation.get("localId") or annotation.get("id") or (annotation.get("pinnedAt"), annotation.get("text"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(annotation)
    return merged


def recover_ignition_annotations(profile, ignition_annotations) -> list[dict]:
    signals_by_path = {signal.tag.full_path: signal for signal in TraceSignal.objects.select_related("tag")}
    existing_targets = {
        str(target.ignition_storage_id): target
        for target in TraceAnnotationTarget.objects.select_related("annotation").filter(
            ignition_storage_id__in=[annotation.storage_id for annotation in ignition_annotations if annotation.storage_id]
        )
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
