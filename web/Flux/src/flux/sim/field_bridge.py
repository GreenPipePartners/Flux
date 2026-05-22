from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from django.db import transaction

from flux.base.models import FieldDevice, FieldEndpoint, FieldTag, SimDevice, SimDeviceTag, SimServer


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
    devices = SimDevice.objects.filter(enabled=True).select_related("provider", "driver")
    if provider_name:
        devices = devices.filter(provider__name=provider_name)
    devices = devices.prefetch_related("tags").order_by("provider__name", "name")

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
            _endpoint, field_device = materialize_sim_device(sim_device, enabled_tags, endpoint=endpoint)
            device_count += 1
            tag_count += field_device.tags.filter(enabled=True).count()

    return FieldBridgeResult(
        endpoint_count=len(endpoints_by_server), device_count=device_count, tag_count=tag_count
    )


def materialize_sim_device(
    sim_device: SimDevice, enabled_tags: list[SimDeviceTag] | None = None, *, endpoint: FieldEndpoint | None = None
) -> tuple[FieldEndpoint, FieldDevice]:
    tags = (
        enabled_tags
        if enabled_tags is not None
        else list(sim_device.tags.filter(enabled=True).order_by("source_path"))
    )
    endpoint = endpoint or materialize_sim_server_endpoint(sim_device=sim_device)
    field_device, _created = FieldDevice.objects.update_or_create(
        endpoint=endpoint,
        name=sim_device.name,
        defaults={
            "device_type": sim_device.driver.label,
            "browse_path": sim_device.provider.name,
            "enabled": True,
            "description": "Materialized from SimDevice catalog %s" % sim_device.id,
            "config": sim_device_runtime_config(sim_device),
        },
    )

    tag_names = field_tag_names(tags)
    active_names = set(tag_names.values())
    for sim_tag in tags:
        FieldTag.objects.update_or_create(
            device=field_device,
            name=tag_names[sim_tag.id],
            defaults={
                "data_type": field_data_type(sim_tag.data_type),
                "update_rate_ms": sim_device.config.get("update_rate_ms", 1000),
                "simulation_type": FieldTag.SimulationType.STATIC,
                "min_value": None,
                "max_value": None,
                "variance": 0.0,
                "initial_value": "",
                "enabled": True,
                "description": sim_tag.source_path,
                "config": sim_tag_runtime_config(sim_tag),
            },
        )
    field_device.tags.exclude(name__in=active_names).update(enabled=False)
    return endpoint, field_device


def materialize_sim_server_endpoint(*, sim_server: SimServer | None = None) -> FieldEndpoint:
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


def sim_server_for_device(sim_device: SimDevice) -> SimServer:
    return sim_device.provider.sim_server or default_sim_server()


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


def field_endpoint_name(sim_device: SimDevice) -> str:
    value = "sim-%s-%s" % (safe_name(sim_device.provider.name), safe_name(sim_device.name))
    if len(value) <= 120:
        return value
    digest = sha1(value.encode("utf-8")).hexdigest()[:10]
    return "%s-%s" % (value[:109], digest)


def sim_device_runtime_config(sim_device: SimDevice) -> dict[str, object]:
    # Device mode is server/request-level behavior. Per-tag write behavior belongs
    # on SimDeviceTag/tag-mode configuration, not on this FieldDevice boundary.
    config: dict[str, object] = {
        "source": "sim_device",
        "sim_device_id": sim_device.id,
        "mode": sim_device.mode,
    }
    if sim_device.mode == SimDevice.Mode.SLOW_NETWORK:
        config["response_delay_ms"] = sim_device.response_delay_ms
    return config


def sim_tag_runtime_config(sim_tag: SimDeviceTag) -> dict[str, object]:
    config: dict[str, object] = {
        "source": "sim_device_tag",
        "sim_device_tag_id": sim_tag.id,
        "source_path": sim_tag.source_path,
        "behavior": sim_tag.behavior,
    }
    if sim_tag.mode_config:
        config["mode_config"] = sim_tag.mode_config
    return config


def field_tag_names(tags: list[SimDeviceTag]) -> dict[int, str]:
    totals: dict[str, int] = {}
    for tag in tags:
        totals[tag.tag_name] = totals.get(tag.tag_name, 0) + 1

    names: dict[int, str] = {}
    for tag in tags:
        if totals[tag.tag_name] == 1:
            names[tag.id] = tag.tag_name
        else:
            names[tag.id] = "%s__%s" % (
                tag.tag_name,
                sha1(tag.source_path.encode("utf-8")).hexdigest()[:8],
            )
    return names


def field_data_type(data_type: str) -> str:
    normalized = data_type.lower()
    if "bool" in normalized:
        return FieldTag.DataType.BOOL
    if "float" in normalized or "double" in normalized:
        return FieldTag.DataType.FLOAT
    if "int" in normalized:
        return FieldTag.DataType.INT
    return FieldTag.DataType.STRING


def safe_name(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in "-_" else "_" for character in value
    )
