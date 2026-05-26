from __future__ import annotations

from typing import Any

from flux.base.models import Device, Tag
from flux.sim.models import DeviceConfig, TagConfig


SYNC_BATCH_SIZE = 5000


def upsert_device_config(
    *,
    namespace: str,
    name: str,
    device_type: str,
    endpoint: Any = None,
    source_provider: Any = None,
    sim_server: Any = None,
    driver: Any = None,
    browse_path: str = "Devices",
    mode: str = DeviceConfig.Mode.STANDARD,
    response_delay_ms: int = 0,
    source_status: str = "",
    source_detail: str = "",
    enabled: bool = True,
    description: str = "",
    config: dict[str, Any] | None = None,
) -> DeviceConfig:
    base_device = upsert_base_device(
        namespace=namespace,
        name=name,
        device_type=device_type or "generic",
        enabled=enabled,
        description=description,
    )
    return DeviceConfig.objects.update_or_create(
        base_device=base_device,
        defaults={
            "endpoint": endpoint,
            "source_provider": source_provider,
            "sim_server": sim_server,
            "driver": driver,
            "browse_path": browse_path or "Devices",
            "mode": mode or DeviceConfig.Mode.STANDARD,
            "response_delay_ms": response_delay_ms or 0,
            "source_status": source_status or "",
            "source_detail": source_detail or "",
            "enabled": enabled,
            "config": config or {},
        },
    )[0]


def upsert_tag_config(
    *,
    sim_device: DeviceConfig,
    provider: str,
    tagpath: str,
    tag_name: str,
    data_type: str,
    update_rate_ms: int = 1000,
    simulation_type: str = TagConfig.SimulationType.RAMP,
    min_value: float | None = None,
    max_value: float | None = None,
    variance: float = 0.0,
    initial_value: str = "",
    source_tag_node: Any = None,
    source_path: str = "",
    behavior: str = TagConfig.Behavior.IMMEDIATE,
    address_strategy: str = "generic",
    address: dict[str, Any] | None = None,
    mode_config: dict[str, Any] | None = None,
    enabled: bool = True,
    materialized: bool = False,
    description: str = "",
    config: dict[str, Any] | None = None,
) -> TagConfig:
    if not isinstance(update_rate_ms, int) or update_rate_ms <= 0:
        update_rate_ms = 1000
    base_tag = upsert_base_tag(
        provider=provider,
        tagpath=tagpath,
        device=sim_device.base_device,
        name=tag_name or tagpath.rsplit("/", 1)[-1],
        data_type=data_type or "",
        update_rate_ms=update_rate_ms,
        enabled=enabled,
        description=description or source_path,
    )
    return TagConfig.objects.update_or_create(
        sim_device=sim_device,
        base_tag=base_tag,
        defaults={
            "source_tag_node": source_tag_node,
            "source_path": source_path or "",
            "tag_name": tag_name or "",
            "simulation_type": simulation_type or TagConfig.SimulationType.RAMP,
            "min_value": min_value,
            "max_value": max_value,
            "variance": variance,
            "initial_value": initial_value or "",
            "behavior": behavior or TagConfig.Behavior.IMMEDIATE,
            "address_strategy": address_strategy or "generic",
            "address": address or {},
            "mode_config": mode_config,
            "enabled": enabled,
            "materialized": materialized,
            "config": config or {},
        },
    )[0]


def disable_materialized_configs(sim_device: DeviceConfig, active_tag_names: set[str]) -> None:
    TagConfig.objects.filter(sim_device=sim_device, materialized=True).exclude(
        config__has_key="rehydrated_source_path"
    ).exclude(tag_name__in=active_tag_names).update(materialized=False)


def delete_materialized_configs_for_source_paths(provider: str, source_paths: list[str]) -> None:
    if source_paths:
        TagConfig.objects.filter(base_tag__provider=provider, base_tag__tagpath__in=source_paths, materialized=True).update(
            materialized=False
        )


def disable_sim_catalog_tags(provider_name: str, source_paths: list[str]) -> None:
    if source_paths:
        TagConfig.objects.filter(
            base_tag__provider=provider_name,
            base_tag__tagpath__in=source_paths,
            materialized=False,
        ).update(enabled=False)


def cleanup_empty_runtime_devices() -> None:
    for device in DeviceConfig.objects.filter(endpoint_id__isnull=False, tags__isnull=True):
        device.enabled = False
        device.endpoint = None
        device.save(update_fields=["enabled", "endpoint", "updated_at"])


def upsert_base_device(
    *, namespace: str, name: str, device_type: str, enabled: bool, description: str
) -> Device:
    return Device.objects.update_or_create(
        namespace=namespace,
        name=name,
        defaults={"device_type": device_type, "enabled": enabled, "description": description},
    )[0]


def upsert_base_tag(
    *,
    provider: str,
    tagpath: str,
    device: Device | None,
    name: str,
    data_type: str,
    update_rate_ms: int,
    enabled: bool,
    description: str,
) -> Tag:
    return Tag.objects.update_or_create(
        provider=provider,
        tagpath=tagpath,
        defaults={
            "device": device,
            "full_path": tag_full_path(provider, tagpath),
            "name": name,
            "data_type": data_type,
            "update_rate_ms": update_rate_ms,
            "enabled": enabled,
            "description": description,
        },
    )[0]


def tag_full_path(provider: str, tagpath: str) -> str:
    return "[%s]%s" % (provider, tagpath) if tagpath else "[%s]" % provider


def simulation_type_for_data_type(data_type: str) -> str:
    normalized = data_type.lower()
    if "bool" in normalized:
        return TagConfig.SimulationType.TOGGLE
    if "string" in normalized:
        return TagConfig.SimulationType.STATIC
    return TagConfig.SimulationType.RAMP
