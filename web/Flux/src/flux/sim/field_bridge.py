from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from django.db import transaction

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import SimServer
from flux.sim.kernel_sync import disable_materialized_configs, upsert_device_config, upsert_tag_config
from flux.sim.models import DeviceConfig, TagConfig


DEFAULT_ENDPOINT_URL = "opc.tcp://0.0.0.0:4840/flux/sim"
DEFAULT_APPLICATION_URI = "urn:flux:sim"
DEFAULT_PRODUCT_URI = "urn:flux:sim"
DEFAULT_NAMESPACE_URI = "urn:flux:sim"
DEFAULT_SIM_SERVER_NAME = "Flux sim OPC-UA Server"


@dataclass(frozen=True)
class FieldBridgeResult:
    endpoint_count: int
    device_count: int
    tag_count: int


def materialize_enabled_sim_devices(*, provider_name: str | None = None) -> FieldBridgeResult:
    devices = DeviceConfig.objects.filter(enabled=True, source_provider_id__isnull=False).select_related(
        "base_device", "source_provider", "source_provider__sim_server", "sim_server", "driver"
    )
    if provider_name:
        devices = devices.filter(source_provider__name=provider_name)
    devices = devices.prefetch_related("tags__base_tag", "tags__source_tag_node").order_by(
        "source_provider__name", "base_device__name"
    )

    device_count = 0
    tag_count = 0
    with transaction.atomic():
        endpoints_by_server: dict[int, FieldEndpoint] = {}
        for sim_device in devices:
            enabled_tags = list(sim_device.tags.filter(enabled=True).order_by("source_path"))
            if not enabled_tags:
                continue

            sim_server = sim_server_for_device(sim_device)
            endpoint = endpoints_by_server.get(sim_server.id)
            if endpoint is None:
                endpoint = materialize_sim_server_endpoint(sim_server=sim_server)
                endpoints_by_server[sim_server.id] = endpoint
            _endpoint, device_config = materialize_sim_device(sim_device, enabled_tags, endpoint=endpoint)
            device_count += 1
            tag_count += device_config.tags.filter(materialized=True, enabled=True).count()

    return FieldBridgeResult(
        endpoint_count=len(endpoints_by_server), device_count=device_count, tag_count=tag_count
    )


def materialize_sim_device(
    sim_device: DeviceConfig, enabled_tags: list[TagConfig] | None = None, *, endpoint: FieldEndpoint | None = None
) -> tuple[FieldEndpoint, DeviceConfig]:
    tags = (
        enabled_tags
        if enabled_tags is not None
        else list(sim_device.tags.filter(enabled=True).select_related("base_tag", "source_tag_node").order_by("source_path"))
    )
    endpoint = endpoint or materialize_sim_server_endpoint(sim_device=sim_device)
    base_device = sim_device.base_device
    device_config = upsert_device_config(
        namespace=base_device.namespace,
        name=base_device.name,
        device_type=base_device.device_type,
        endpoint=endpoint,
        source_provider=sim_device.source_provider,
        sim_server=sim_device.sim_server or (sim_device.source_provider.sim_server if sim_device.source_provider_id else None),
        driver=sim_device.driver,
        browse_path=sim_device.browse_path,
        mode=sim_device.mode,
        response_delay_ms=sim_device.response_delay_ms if sim_device.mode == DeviceConfig.Mode.SLOW_NETWORK else 0,
        source_status=sim_device.source_status,
        source_detail=sim_device.source_detail,
        enabled=True,
        description="Materialized from sim.device catalog %s" % sim_device.id,
        config=sim_device_runtime_config(sim_device),
    )

    tag_names = field_tag_names(tags)
    active_names = set(tag_names.values())
    for sim_tag in tags:
        simulation_defaults = field_tag_simulation_defaults(sim_tag)
        upsert_tag_config(
            sim_device=device_config,
            provider=sim_tag.base_tag.provider,
            tagpath=sim_tag.base_tag.tagpath,
            tag_name=tag_names[sim_tag.id],
            data_type=field_data_type(sim_tag.base_tag.data_type),
            update_rate_ms=sim_tag.base_tag.update_rate_ms,
            simulation_type=simulation_defaults["simulation_type"],
            min_value=simulation_defaults["min_value"],
            max_value=simulation_defaults["max_value"],
            variance=simulation_defaults["variance"],
            initial_value=simulation_defaults["initial_value"],
            source_tag_node=sim_tag.source_tag_node,
            source_path=sim_tag.source_path,
            behavior=sim_tag.behavior,
            address_strategy=sim_tag.address_strategy,
            address=sim_tag.address,
            mode_config=sim_tag.mode_config,
            enabled=True,
            materialized=True,
            description=sim_tag.source_path,
            config=sim_tag_runtime_config(sim_tag),
        )
    disable_materialized_configs(device_config, active_names)
    return endpoint, device_config


def materialize_sim_server_endpoint(*, sim_server: SimServer | None = None, sim_device: DeviceConfig | None = None) -> FieldEndpoint:
    if sim_server is None and sim_device is not None:
        sim_server = sim_server_for_device(sim_device)
    sim_server = sim_server or default_sim_server()
    return FieldEndpoint.objects.update_or_create(
        name=sim_server.name,
        defaults={
            "endpoint_url": sim_server.endpoint_url or DEFAULT_ENDPOINT_URL,
            "application_uri": sim_server.application_uri or DEFAULT_APPLICATION_URI,
            "product_uri": sim_server.product_uri or DEFAULT_PRODUCT_URI,
            "namespace_uri": sim_server.namespace_uri or DEFAULT_NAMESPACE_URI,
            "enabled": sim_server.enabled,
            "security_policy": sim_server.security_policy or "None",
        },
    )[0]


def sim_server_for_device(sim_device: DeviceConfig) -> SimServer:
    return sim_device.sim_server or (sim_device.source_provider.sim_server if sim_device.source_provider_id else None) or default_sim_server()


def default_sim_server() -> SimServer:
    return SimServer.objects.get_or_create(
        name=DEFAULT_SIM_SERVER_NAME,
        defaults={
            "endpoint_url": DEFAULT_ENDPOINT_URL,
            "application_uri": DEFAULT_APPLICATION_URI,
            "product_uri": DEFAULT_PRODUCT_URI,
            "namespace_uri": DEFAULT_NAMESPACE_URI,
            "enabled": True,
            "security_policy": "None",
        },
    )[0]


def sim_device_runtime_config(sim_device: DeviceConfig) -> dict[str, object]:
    # Device mode is server/request-level behavior. Per-tag write behavior belongs
    # on TagConfig/tag-mode configuration, not on this device boundary.
    config: dict[str, object] = {
        "source": "sim_device_config",
        "sim_device_config_id": sim_device.id,
        "mode": sim_device.mode,
    }
    if sim_device.mode == DeviceConfig.Mode.SLOW_NETWORK:
        config["response_delay_ms"] = sim_device.response_delay_ms
    return config


def sim_tag_runtime_config(sim_tag: TagConfig) -> dict[str, object]:
    config: dict[str, object] = {
        "source": "sim_tag_config",
        "sim_tag_config_id": sim_tag.id,
        "source_path": sim_tag.source_path,
        "behavior": sim_tag.behavior,
    }
    if sim_tag.mode_config:
        config["mode_config"] = sim_tag.mode_config
    return config


def field_tag_simulation_defaults(sim_tag: TagConfig) -> dict[str, object]:
    mode_config = sim_tag.mode_config or {}
    return {
        "simulation_type": mode_config.get("simulation_type") or TagConfig.SimulationType.STATIC,
        "min_value": mode_config.get("min_value"),
        "max_value": mode_config.get("max_value"),
        "variance": mode_config.get("variance", 0.0),
        "initial_value": bounded_field_value(mode_config.get("initial_value") or "", max_length=255),
    }


def field_tag_names(tags: list[TagConfig]) -> dict[int, str]:
    totals: dict[str, int] = {}
    for tag in tags:
        totals[tag.name] = totals.get(tag.name, 0) + 1

    names: dict[int, str] = {}
    for tag in tags:
        if totals[tag.name] == 1:
            names[tag.id] = bounded_field_value(tag.name, max_length=255)
        else:
            names[tag.id] = bounded_field_value("%s__%s" % (
                tag.name,
                sha1(tag.source_path.encode("utf-8")).hexdigest()[:8],
            ), max_length=255)
    return names


def bounded_field_value(value: object, *, max_length: int) -> str:
    text = str(value or "")
    if len(text) <= max_length:
        return text
    return text[:max_length]


def field_data_type(data_type: str) -> str:
    normalized = data_type.lower()
    if "bool" in normalized:
        return Tag.DataType.BOOL
    if "float" in normalized or "double" in normalized:
        return Tag.DataType.FLOAT
    if "int" in normalized:
        return Tag.DataType.INT
    return Tag.DataType.STRING


def safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "_" for character in value
    )
