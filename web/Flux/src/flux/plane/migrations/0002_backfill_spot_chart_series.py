import hashlib
import re

from django.db import migrations


BATCH_SIZE = 5000


def entity_key_hash(kind: str, natural_key: str) -> str:
    return hashlib.sha256(f"{kind}\0{natural_key}".encode("utf-8")).hexdigest()


def tag_full_path(provider: str, tagpath: str) -> str:
    return "[%s]%s" % (provider, tagpath) if tagpath else "[%s]" % provider


def parse_full_tag_path(full_path: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"\[([^\]]+)](.+)", (full_path or "").strip())
    if not match:
        return None
    provider, tagpath = match.groups()
    return provider, tagpath.strip("/")


def backfill_spot_chart_series(apps, schema_editor):
    Entity = apps.get_model("base", "Entity")
    Tag = apps.get_model("base", "Tag")
    Series = apps.get_model("plane", "Series")
    Point = apps.get_model("live", "LiveCardPointDefinition")
    Signal = apps.get_model("trace", "TraceSignal")

    pending_points = []
    for point in Point.objects.all().only("id", "full_path", "label", "enabled", "series_id").iterator(chunk_size=BATCH_SIZE):
        if point.series_id:
            continue
        parsed = parse_full_tag_path(point.full_path)
        if parsed is None:
            continue
        pending_points.append(point)
        if len(pending_points) >= BATCH_SIZE:
            flush_spot_points(Entity, Tag, Series, Point, pending_points)
            pending_points = []
    if pending_points:
        flush_spot_points(Entity, Tag, Series, Point, pending_points)

    pending_signals = []
    for signal in Signal.objects.select_related("tag", "tag__schedule").only(
        "id",
        "series_id",
        "tag__provider",
        "tag__path",
        "tag__display_name",
        "tag__enabled",
        "tag__schedule__interval_seconds",
    ).iterator(chunk_size=BATCH_SIZE):
        if signal.series_id:
            continue
        pending_signals.append(signal)
        if len(pending_signals) >= BATCH_SIZE:
            flush_chart_signals(Entity, Tag, Series, Signal, pending_signals)
            pending_signals = []
    if pending_signals:
        flush_chart_signals(Entity, Tag, Series, Signal, pending_signals)


def flush_spot_points(Entity, Tag, Series, Point, points):
    specs = []
    for point in points:
        parsed = parse_full_tag_path(point.full_path)
        if parsed is None:
            continue
        provider, tagpath = parsed
        full_path = tag_full_path(provider, tagpath)
        specs.append(
            {
                "row": point,
                "provider": provider,
                "tagpath": tagpath,
                "full_path": full_path,
                "name": point.label or tagpath.rsplit("/", 1)[-1],
                "enabled": point.enabled,
                "update_rate_ms": 1000,
            }
        )
    link_rows(Entity, Tag, Series, Point, specs)


def flush_chart_signals(Entity, Tag, Series, Signal, signals):
    specs = []
    for signal in signals:
        tagpath = (signal.tag.path or "").strip("/")
        if not signal.tag.provider or not tagpath:
            continue
        full_path = tag_full_path(signal.tag.provider, tagpath)
        interval_seconds = signal.tag.schedule.interval_seconds if signal.tag.schedule_id else 1
        specs.append(
            {
                "row": signal,
                "provider": signal.tag.provider,
                "tagpath": tagpath,
                "full_path": full_path,
                "name": signal.tag.display_name or tagpath.rsplit("/", 1)[-1],
                "enabled": signal.tag.enabled,
                "update_rate_ms": max(1, interval_seconds) * 1000,
            }
        )
    link_rows(Entity, Tag, Series, Signal, specs)


def link_rows(Entity, Tag, Series, RowModel, specs):
    if not specs:
        return
    ensure_base_tags(Entity, Tag, specs)
    tags_by_full_path = {
        tag.full_path: tag
        for tag in Tag.objects.filter(full_path__in={spec["full_path"] for spec in specs}).only(
            "id", "entity_id", "full_path", "name", "enabled", "update_rate_ms"
        )
    }
    ensure_series(Entity, Series, tags_by_full_path.values())
    series_by_tag_id = {
        series.base_tag_id: series
        for series in Series.objects.filter(base_tag_id__in=[tag.id for tag in tags_by_full_path.values()]).only(
            "id", "base_tag_id"
        )
    }
    updates = []
    for spec in specs:
        tag = tags_by_full_path.get(spec["full_path"])
        if tag is None:
            continue
        series = series_by_tag_id.get(tag.id)
        if series is None:
            continue
        spec["row"].series_id = series.id
        updates.append(spec["row"])
    if updates:
        RowModel.objects.bulk_update(updates, ["series"], batch_size=BATCH_SIZE)


def ensure_base_tags(Entity, Tag, specs):
    kind = "base.tag"
    entities = []
    for spec in specs:
        key_hash = entity_key_hash(kind, spec["full_path"])
        entities.append(
            Entity(
                kind=kind,
                natural_key=spec["full_path"],
                natural_key_hash=key_hash,
                display_name=spec["name"][:255],
            )
        )
    Entity.objects.bulk_create(entities, ignore_conflicts=True, batch_size=BATCH_SIZE)
    entities_by_hash = {
        entity.natural_key_hash: entity
        for entity in Entity.objects.filter(
            kind=kind,
            natural_key_hash__in=[entity_key_hash(kind, spec["full_path"]) for spec in specs],
        ).only("id", "natural_key_hash")
    }
    tags = []
    for spec in specs:
        entity = entities_by_hash[entity_key_hash(kind, spec["full_path"])]
        tags.append(
            Tag(
                entity_id=entity.id,
                provider=spec["provider"],
                tagpath=spec["tagpath"],
                full_path=spec["full_path"],
                name=spec["name"],
                data_type="",
                update_rate_ms=spec["update_rate_ms"],
                enabled=spec["enabled"],
                description="Materialized from Spot/Chart membership",
            )
        )
    Tag.objects.bulk_create(tags, ignore_conflicts=True, batch_size=BATCH_SIZE)
    existing_tags = list(
        Tag.objects.filter(full_path__in={spec["full_path"] for spec in specs}, entity_id__isnull=True).only(
            "id", "full_path", "entity_id"
        )
    )
    for tag in existing_tags:
        tag.entity_id = entities_by_hash[entity_key_hash(kind, tag.full_path)].id
    if existing_tags:
        Tag.objects.bulk_update(existing_tags, ["entity"], batch_size=BATCH_SIZE)


def ensure_series(Entity, Series, tags):
    kind = "plane.series"
    tags = list(tags)
    entities = []
    for tag in tags:
        key_hash = entity_key_hash(kind, tag.full_path)
        entities.append(
            Entity(
                kind=kind,
                natural_key=tag.full_path,
                natural_key_hash=key_hash,
                display_name=(tag.name or tag.full_path.rsplit("/", 1)[-1])[:255],
            )
        )
    Entity.objects.bulk_create(entities, ignore_conflicts=True, batch_size=BATCH_SIZE)
    entities_by_hash = {
        entity.natural_key_hash: entity
        for entity in Entity.objects.filter(
            kind=kind,
            natural_key_hash__in=[entity_key_hash(kind, tag.full_path) for tag in tags],
        ).only("id", "natural_key_hash")
    }
    series_rows = []
    for tag in tags:
        series_rows.append(
            Series(
                entity_id=entities_by_hash[entity_key_hash(kind, tag.full_path)].id,
                base_tag_id=tag.id,
                enabled=tag.enabled,
                latest_enabled=True,
                history_enabled=True,
                sample_interval_ms=tag.update_rate_ms or 1000,
                storage_key=tag.full_path,
            )
        )
    Series.objects.bulk_create(series_rows, ignore_conflicts=True, batch_size=BATCH_SIZE)
    existing_series = list(
        Series.objects.select_related("base_tag").filter(
            base_tag_id__in=[tag.id for tag in tags],
            entity_id__isnull=True,
        ).only("id", "entity_id", "base_tag__full_path")
    )
    for series in existing_series:
        series.entity_id = entities_by_hash[entity_key_hash(kind, series.base_tag.full_path)].id
    if existing_series:
        Series.objects.bulk_update(existing_series, ["entity"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):

    dependencies = [
        ("plane", "0001_initial"),
        ("live", "0002_point_series"),
        ("trace", "0003_signal_series"),
    ]

    operations = [migrations.RunPython(backfill_spot_chart_series, migrations.RunPython.noop)]
