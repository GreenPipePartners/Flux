from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from django.db import transaction

from flux.base.runtime import RuntimeTag, TagSchedule
from flux.plane.services import ensure_series_for_full_path
from flux.trace.models import TraceProfile, TraceSignal


TRACE_SCOPE_SCHEDULE = "trace-csv-60s"
TRACE_SCOPE_HISTORY_PROVIDER = "Core Historian"


@dataclass(frozen=True)
class TraceScopeImportResult:
    profiles: int
    tags: int
    signals: int


def import_trace_scopes_csv(csv_source: str | Path | IO[str]) -> TraceScopeImportResult:
    close_source = False
    if isinstance(csv_source, str | Path):
        csv_file = open(csv_source, newline="", encoding="utf-8")
        close_source = True
    else:
        csv_file = csv_source
    try:
        return import_trace_scopes_rows(csv.DictReader(csv_file))
    finally:
        if close_source:
            csv_file.close()


def import_trace_scopes_rows(rows: csv.DictReader) -> TraceScopeImportResult:
    schedule, _created = TagSchedule.objects.update_or_create(
        name=TRACE_SCOPE_SCHEDULE,
        defaults={"interval_seconds": 60, "enabled": True},
    )
    profile_count = 0
    tag_count = 0
    signal_count = 0
    with transaction.atomic():
        for row in rows:
            normalized = normalize_row(row)
            scope = slug(normalized.get("chart scope") or normalized.get("id") or "")
            if not scope:
                continue
            tag_refs = tag_references(normalized)
            if not tag_refs:
                continue
            profile, _created = TraceProfile.objects.update_or_create(
                key=scope,
                defaults={
                    "label": normalized.get("name") or normalized.get("id") or scope,
                    "enabled": True,
                    "cache_enabled": True,
                    "history_provider": TRACE_SCOPE_HISTORY_PROVIDER,
                    "sync_interval_seconds": 60,
                },
            )
            profile_count += 1
            runtime_tags = []
            for sort_order, full_path in enumerate(tag_refs, start=1):
                provider, path = parse_full_tag_path(full_path)
                display_name = path.rstrip("/").rsplit("/", 1)[-1]
                series = ensure_series_for_full_path(full_path)
                runtime_tag, _created = RuntimeTag.objects.update_or_create(
                    provider=provider,
                    path=path,
                    defaults={
                        "display_name": display_name,
                        "asset_name": profile.label,
                        "schedule": schedule,
                        "enabled": True,
                    },
                )
                runtime_tags.append(runtime_tag)
                tag_count += 1
                TraceSignal.objects.update_or_create(
                    profile=profile,
                    tag=runtime_tag,
                    defaults={
                        "label": display_name,
                        "series": series,
                        "sort_order": sort_order,
                        "default_visible": True,
                        "cache_enabled": True,
                    },
                )
                signal_count += 1
            profile.signals.exclude(tag__in=runtime_tags).delete()
    return TraceScopeImportResult(profiles=profile_count, tags=tag_count, signals=signal_count)


def normalize_row(row: dict[str, str | None]) -> dict[str, str]:
    return {normalize_header(key): (value or "").strip() for key, value in row.items() if key is not None}


def normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip().lower())


def tag_references(row: dict[str, str]) -> list[str]:
    tag_columns = [key for key in row if re.fullmatch(r"tag \d+", key)]
    tag_columns.sort(key=lambda key: int(key.rsplit(" ", 1)[-1]))
    return [row[key] for key in tag_columns if row[key]]


def parse_full_tag_path(full_path: str) -> tuple[str, str]:
    match = re.fullmatch(r"\[([^\]]+)](.+)", full_path.strip())
    if not match:
        raise ValueError(f"Trace CSV tag must use full [provider]path form: {full_path}")
    provider, path = match.groups()
    return provider, path.strip("/")


def slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.strip().lower())).strip("-")
