from __future__ import annotations

import json
import uuid

from django.utils.dateparse import parse_datetime

from flux.base.annotations import (
    AnnotationTargetWrite,
    create_trace_annotation,
    local_trace_annotations,
    recover_ignition_trace_annotations,
    trace_annotation_profile,
    update_trace_annotation_target_qualities,
)
from flux.chart import annotation_bridge


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

    annotation_id = str(uuid.uuid4())
    storage_ids = [str(uuid.uuid4()) for _path in paths]
    profile = trace_annotation_profile(str(payload.get("profileKey") or ""))
    annotation = create_trace_annotation(
        profile=profile,
        marker_id=payload.get("markerId"),
        marker_time=marker_time,
        text=text,
        targets=[AnnotationTargetWrite(historian_path=path, ignition_storage_id=storage_id) for path, storage_id in zip(paths, storage_ids, strict=True)],
    )
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
    update_trace_annotation_target_qualities(annotation, [str(quality) for quality in (qualities or [])])
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


def query_saved_annotations(payload: dict) -> dict:
    paths = payload.get("paths") or []
    start_time = payload.get("startTime")
    end_time = payload.get("endTime")
    if not isinstance(paths, list) or not paths:
        raise TraceAnnotationError("At least one historian path is required")
    if start_time is None or end_time is None:
        raise TraceAnnotationError("startTime and endTime are required")
    profile = trace_annotation_profile(str(payload.get("profileKey") or ""))
    return {
        "annotations": local_trace_annotations(profile=profile, paths=paths, start_time=int(start_time), end_time=int(end_time)),
        "warning": "",
    }


def store_ignition_annotations(*, paths: list[str], marker_ms: int, storage_ids: list[str], annotation_data: str):
    return annotation_bridge.store_ignition_annotations(
        paths=paths,
        marker_ms=marker_ms,
        storage_ids=storage_ids,
        annotation_data=annotation_data,
    )


def query_ignition_annotations(*, paths: list[str], start_time: int, end_time: int):
    return annotation_bridge.query_ignition_annotations(paths=paths, start_time=start_time, end_time=end_time)


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
    return recover_ignition_trace_annotations(profile, ignition_annotations)
