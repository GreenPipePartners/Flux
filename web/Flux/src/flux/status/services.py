from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from flux.base.models import Entity, entity_key_hash
from flux.status.models import LatestStatus


@dataclass(frozen=True)
class LatestStatusUpdate:
    entity: Entity
    status_kind: str
    observed_state: str
    severity: str
    summary: str
    source: str
    source_instance: str = ""
    detail: str = ""
    last_seen_at: Any = None
    stale_after_seconds: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def ensure_entity(*, kind: str, natural_key: str, display_name: str) -> Entity:
    key_hash = entity_key_hash(kind, natural_key)
    entity, _created = Entity.objects.update_or_create(
        kind=kind,
        natural_key_hash=key_hash,
        defaults={"natural_key": natural_key, "display_name": display_name[:255]},
    )
    return entity


def upsert_latest_status(
    *,
    entity: Entity,
    status_kind: str,
    observed_state: str,
    severity: str,
    summary: str,
    source: str,
    source_instance: str = "",
    detail: str = "",
    last_seen_at=None,
    stale_after_seconds: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> LatestStatus:
    status, _created = LatestStatus.objects.update_or_create(
        entity=entity,
        status_kind=status_kind,
        source=source,
        source_instance=source_instance,
        defaults={
            "observed_state": observed_state,
            "severity": severity,
            "summary": summary[:255],
            "detail": detail,
            "last_seen_at": last_seen_at,
            "stale_after_seconds": stale_after_seconds,
            "evidence": evidence or {},
        },
    )
    return status


def bulk_upsert_latest_status(updates: Iterable[LatestStatusUpdate], *, batch_size: int = 5000) -> int:
    rows = [
        LatestStatus(
            entity=update.entity,
            status_kind=update.status_kind,
            observed_state=update.observed_state,
            severity=update.severity,
            summary=update.summary[:255],
            detail=update.detail,
            last_seen_at=update.last_seen_at,
            stale_after_seconds=update.stale_after_seconds,
            source=update.source,
            source_instance=update.source_instance,
            evidence=update.evidence,
        )
        for update in updates
    ]
    if not rows:
        return 0
    LatestStatus.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["entity", "status_kind", "source", "source_instance"],
        update_fields=[
            "observed_state",
            "severity",
            "summary",
            "detail",
            "last_seen_at",
            "stale_after_seconds",
            "evidence",
            "updated_at",
        ],
        batch_size=batch_size,
    )
    return len(rows)


def record_worker_status(
    *,
    service_name: str,
    instance_id: str,
    observed_state: str,
    severity: str,
    summary: str,
    last_seen_at,
    evidence: dict[str, Any] | None = None,
    detail: str = "",
) -> LatestStatus:
    natural_key = f"{service_name}:{instance_id}"
    entity = ensure_entity(kind=Entity.Kind.SERVE_WORKER, natural_key=natural_key, display_name=service_name)
    return upsert_latest_status(
        entity=entity,
        status_kind=LatestStatus.StatusKind.WORKER,
        observed_state=observed_state,
        severity=severity,
        summary=summary,
        detail=detail,
        last_seen_at=last_seen_at,
        source="serve.worker",
        source_instance=instance_id,
        evidence=evidence or {},
    )
