from __future__ import annotations

from .models import RuntimeSchedulerConfig, RuntimeTag


def scheduler_config() -> RuntimeSchedulerConfig:
    return RuntimeSchedulerConfig.default()


def assign_balancer_codes(tags: list[RuntimeTag], *, config: RuntimeSchedulerConfig | None = None) -> list[RuntimeTag]:
    config = config or scheduler_config()
    bucket_count = max(config.cold_bucket_count, 1)
    changed: list[RuntimeTag] = []
    for index, tag in enumerate(tags):
        expected_code = (index % bucket_count) + 1
        if tag.balancer_code == expected_code:
            continue
        tag.balancer_code = expected_code
        changed.append(tag)
    if changed:
        RuntimeTag.objects.bulk_update(changed, ["balancer_code"])
    return tags


def advance_balancer_code(*, config: RuntimeSchedulerConfig | None = None) -> int:
    config = config or scheduler_config()
    return config.advance_balancer_code()
