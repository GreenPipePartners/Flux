from __future__ import annotations

from datetime import datetime
from typing import Any

from django.utils import timezone

from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample, TagSchedule, assign_balancer_codes, scheduler_config
from flux.base.field_config import ignition_tag_config
from flux.base.models import FieldTag
from flux.sim.field_demo import DEMO_TAG_FOLDER, demo_tag_metadata, ensure_demo_field_config


DEMO_SCHEDULE_NAME = "sim-demo-10s"


def ensure_demo_runtime_config() -> list[RuntimeTag]:
    _endpoint, field_tags = ensure_demo_field_config()
    config = scheduler_config()
    schedule, _created = TagSchedule.objects.update_or_create(
        name=DEMO_SCHEDULE_NAME,
        defaults={"interval_seconds": config.warm_interval_seconds, "enabled": True},
    )
    metadata = demo_tag_metadata()
    runtime_tags: list[RuntimeTag] = []
    for field_tag in field_tags:
        demo_tag = metadata.get((field_tag.device.name, field_tag.name))
        display_name = demo_tag.label if demo_tag and demo_tag.label else field_tag.name.replace("_", " ").title()
        engineering_units = demo_tag.units if demo_tag else ""
        runtime_tag, _created = RuntimeTag.objects.update_or_create(
            provider="default",
            path=f"{DEMO_TAG_FOLDER}/{field_tag.device.name}_{field_tag.name}",
            defaults={
                "display_name": display_name,
                "asset_name": f"{field_tag.device.device_type}: {field_tag.device.name}",
                "engineering_units": engineering_units,
                "category": RuntimeTag.Category.SIMULATION,
                "schedule": schedule,
                "enabled": True,
            },
        )
        runtime_tags.append(runtime_tag)
    return assign_balancer_codes(runtime_tags, config=config)


def configure_demo_ignition_tags(fx: Any, *, opc_server: str = "Flux Field") -> Any:
    _endpoint, field_tags = ensure_demo_field_config()
    return fx.tag.configure(
        [
            {
                "name": DEMO_TAG_FOLDER,
                "tagType": "Folder",
                "tags": [demo_ignition_tag_config(tag, opc_server) for tag in field_tags],
            }
        ],
        base_path="[default]",
        collision_policy="o",
    )


def read_demo_runtime_values(fx: Any, *, runtime_tags: list[RuntimeTag] | None = None) -> int:
    runtime_tags = runtime_tags or ensure_demo_runtime_config()
    if not runtime_tags:
        return 0
    values = fx.tag.read_blocking([tag.full_path for tag in runtime_tags])
    now = timezone.now()
    for runtime_tag, value in zip(runtime_tags, values, strict=True):
        value_timestamp = parse_fluxy_timestamp(value.timestamp) or now
        LatestTagValue.objects.update_or_create(
            tag=runtime_tag,
            defaults={
                "value": value.value,
                "quality_code": value.quality,
                "value_timestamp": value_timestamp,
                "read_at": now,
            },
        )
        TagSample.objects.create(
            tag=runtime_tag,
            value=value.value,
            quality_code=value.quality,
            value_timestamp=value_timestamp,
            read_at=now,
        )
    return len(runtime_tags)


def demo_ignition_tag_config(field_tag: FieldTag, opc_server: str) -> dict[str, Any]:
    return ignition_tag_config(
        field_tag,
        opc_server,
        tag_name=f"{field_tag.device.name}_{field_tag.name}",
    )


def parse_fluxy_timestamp(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    return None
