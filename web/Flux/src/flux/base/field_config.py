from __future__ import annotations

from typing import Any

from flux.sim.models import FieldEndpoint


def enabled_endpoint_configs() -> list[dict[str, Any]]:
    endpoints = FieldEndpoint.objects.filter(enabled=True)
    return [endpoint_config(endpoint) for endpoint in endpoints]


def endpoint_config(endpoint: FieldEndpoint, *, endpoint_url: str | None = None) -> dict[str, Any]:
    sim_devices = endpoint_sim_device_configs(endpoint)
    return {
        "name": endpoint.name,
        "endpoint_url": endpoint_url or endpoint.endpoint_url,
        "application_uri": endpoint.application_uri,
        "product_uri": endpoint.product_uri,
        "namespace_uri": endpoint.namespace_uri,
        "security_policy": endpoint.security_policy,
        "devices": [sim_device_config(device) for device in sim_devices],
    }


def single_device_endpoint_config(device: Any, *, endpoint_url: str | None = None) -> dict[str, Any]:
    endpoint = device.endpoint
    return {
        "name": endpoint.name,
        "endpoint_url": endpoint_url or endpoint.endpoint_url,
        "application_uri": endpoint.application_uri,
        "product_uri": endpoint.product_uri,
        "namespace_uri": endpoint.namespace_uri,
        "security_policy": endpoint.security_policy,
        "devices": [sim_device_config(device)],
    }


def device_config(device: Any) -> dict[str, Any]:
    return sim_device_config(device)


def device_behavior_config(device: Any) -> dict[str, Any]:
    config = sim_device_behavior_config(device)
    return config


def endpoint_sim_device_configs(endpoint: FieldEndpoint) -> list[Any]:
    from flux.sim.models import DeviceConfig

    return list(
        DeviceConfig.objects.filter(endpoint=endpoint, enabled=True)
        .select_related("base_device")
        .prefetch_related("tags__base_tag")
        .order_by("base_device__namespace", "base_device__name")
    )


def sim_device_config(device: Any) -> dict[str, Any]:
    base_device = device.base_device
    tags = list(
        device.tags.filter(materialized=True, enabled=True)
        .select_related("base_tag")
        .order_by("tag_name")
    )
    config = {
        "name": base_device.name,
        "device_type": base_device.device_type,
        "browse_path": device.browse_path,
        "tags": [sim_tag_config(tag) for tag in tags],
    }
    config.update(sim_device_behavior_config(device))
    return config


def sim_device_behavior_config(device: Any) -> dict[str, Any]:
    metadata = device.config or {}
    config: dict[str, Any] = {"metadata": metadata} if metadata else {}
    mode = metadata.get("mode") or (device.mode if device.mode != "standard" else "")
    if mode:
        config["mode"] = mode
    if device.response_delay_ms or "response_delay_ms" in metadata:
        config["response_delay_ms"] = device.response_delay_ms or metadata.get("response_delay_ms", 0)
    return config


def sim_tag_config(tag: Any) -> dict[str, Any]:
    base_tag = tag.base_tag
    device_name = tag.sim_device.base_device.name
    tag_name = tag.tag_name or base_tag.name
    config = {
        "name": tag_name,
        "node_id": f"ns=2;s={device_name}.{tag_name}",
        "browse_name": tag_name,
        "opc_item_path": f"{device_name}/{tag_name}",
        "data_type": base_tag.data_type,
        "update_rate_ms": base_tag.update_rate_ms,
        "simulation_type": tag.simulation_type,
        "min_value": tag.min_value,
        "max_value": tag.max_value,
        "variance": tag.variance,
        "initial_value": tag.initial_value,
    }
    config.update(sim_tag_behavior_config(tag))
    return config


def sim_tag_behavior_config(tag: Any) -> dict[str, Any]:
    config: dict[str, Any] = {}
    metadata = tag.config or {}
    if metadata:
        config["metadata"] = metadata
    behavior = metadata.get("behavior") or (tag.behavior if tag.behavior != "immediate" else "")
    if behavior:
        config["behavior"] = behavior
    mode_config = metadata.get("mode_config") or tag.mode_config
    if mode_config:
        config["mode_config"] = mode_config
    return config


def tag_config(tag: Any) -> dict[str, Any]:
    return sim_tag_config(tag)


def tag_behavior_config(tag: Any) -> dict[str, Any]:
    return sim_tag_behavior_config(tag)


def ignition_tag_config(tag: Any, opc_server: str, tag_name: str | None = None) -> dict[str, Any]:
    return {
        "name": tag_name or tag.name,
        "tagType": "AtomicTag",
        "valueSource": "opc",
        "dataType": tag.ignition_data_type,
        "opcServer": opc_server,
        "opcItemPath": tag.node_id,
    }


def ignition_folder_config(folder_name: str, tags: list[Any], opc_server: str) -> dict[str, Any]:
    return {
        "name": folder_name,
        "tagType": "Folder",
        "tags": [ignition_tag_config(tag, opc_server) for tag in tags],
    }
