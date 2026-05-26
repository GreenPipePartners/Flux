from django.db.models import Count

from .field_config import enabled_endpoint_configs, tag_config as field_tag_config
from flux.sim.models import FieldEndpoint


def materialized_endpoint_ids() -> set[int]:
    from flux.sim.models import DeviceConfig

    return set(
        DeviceConfig.objects.filter(endpoint_id__isnull=False, enabled=True)
        .values_list("endpoint_id", flat=True)
        .distinct()
    )


def endpoint_runtime_counts(endpoint_ids: list[int] | set[int] | None = None) -> dict[int, dict[str, int]]:
    from flux.sim.models import DeviceConfig, TagConfig

    if endpoint_ids is not None and not endpoint_ids:
        return {}
    selected_endpoint_ids = set(endpoint_ids or [])
    device_query = DeviceConfig.objects.filter(endpoint_id__isnull=False, enabled=True)
    tag_query = TagConfig.objects.filter(
        sim_device__endpoint_id__isnull=False,
        sim_device__enabled=True,
        materialized=True,
        enabled=True,
    )
    if selected_endpoint_ids:
        device_query = device_query.filter(endpoint_id__in=selected_endpoint_ids)
        tag_query = tag_query.filter(sim_device__endpoint_id__in=selected_endpoint_ids)

    counts: dict[int, dict[str, int]] = {
        endpoint_id: {"device_count": device_count, "tag_count": 0}
        for endpoint_id, device_count in device_query.values("endpoint_id")
        .annotate(total=Count("id"))
        .values_list("endpoint_id", "total")
    }
    for endpoint_id, tag_count in (
        tag_query.values("sim_device__endpoint_id")
        .annotate(total=Count("id"))
        .values_list("sim_device__endpoint_id", "total")
    ):
        counts.setdefault(endpoint_id, {"device_count": 0, "tag_count": 0})["tag_count"] = tag_count

    return counts


def enabled_runtime_totals() -> dict[str, int]:
    endpoint_ids = set(FieldEndpoint.objects.filter(enabled=True).values_list("id", flat=True))
    counts = endpoint_runtime_counts(endpoint_ids)
    configured_endpoint_ids = {
        endpoint_id for endpoint_id, endpoint_counts in counts.items() if endpoint_counts["device_count"]
    }
    return {
        "endpoint_count": len(configured_endpoint_ids & endpoint_ids),
        "device_count": sum(
            endpoint_counts["device_count"]
            for endpoint_id, endpoint_counts in counts.items()
            if endpoint_id in endpoint_ids
        ),
        "tag_count": sum(
            endpoint_counts["tag_count"]
            for endpoint_id, endpoint_counts in counts.items()
            if endpoint_id in endpoint_ids
        ),
    }


def enabled_field_endpoint_queryset():
    endpoint_ids = [
        endpoint_id
        for endpoint_id, endpoint_counts in endpoint_runtime_counts().items()
        if endpoint_counts["device_count"]
    ]
    return FieldEndpoint.objects.filter(enabled=True, id__in=endpoint_ids).order_by("name")


def endpoint_materialized_tag_count(endpoint: FieldEndpoint) -> int:
    counts = endpoint_runtime_counts({endpoint.id})
    return counts.get(endpoint.id, {"tag_count": 0})["tag_count"]


__all__ = [
    "enabled_endpoint_configs",
    "enabled_field_endpoint_queryset",
    "enabled_runtime_totals",
    "endpoint_materialized_tag_count",
    "endpoint_runtime_counts",
    "field_tag_config",
]
