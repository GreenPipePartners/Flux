from __future__ import annotations

from typing import Any

from .models import FieldDevice, FieldEndpoint, FieldTag


def enabled_endpoint_configs() -> list[dict[str, Any]]:
    endpoints = FieldEndpoint.objects.filter(enabled=True).prefetch_related("devices__tags")
    return [endpoint_config(endpoint) for endpoint in endpoints]


def endpoint_config(endpoint: FieldEndpoint, *, endpoint_url: str | None = None) -> dict[str, Any]:
    devices = FieldDevice.objects.filter(endpoint=endpoint, enabled=True).prefetch_related("tags")
    return {
        "name": endpoint.name,
        "endpoint_url": endpoint_url or endpoint.endpoint_url,
        "application_uri": endpoint.application_uri,
        "product_uri": endpoint.product_uri,
        "namespace_uri": endpoint.namespace_uri,
        "security_policy": endpoint.security_policy,
        "devices": [device_config(device) for device in devices],
    }


def single_device_endpoint_config(device: FieldDevice, *, endpoint_url: str | None = None) -> dict[str, Any]:
    endpoint = device.endpoint
    return {
        "name": endpoint.name,
        "endpoint_url": endpoint_url or endpoint.endpoint_url,
        "application_uri": endpoint.application_uri,
        "product_uri": endpoint.product_uri,
        "namespace_uri": endpoint.namespace_uri,
        "security_policy": endpoint.security_policy,
        "devices": [device_config(device)],
    }


def device_config(device: FieldDevice) -> dict[str, Any]:
    tags = device.tags.filter(enabled=True).order_by("name")
    config = {
        "name": device.name,
        "device_type": device.device_type,
        "browse_path": device.browse_path,
        "tags": [tag_config(tag) for tag in tags],
    }
    config.update(device_behavior_config(device))
    return config


def device_behavior_config(device: FieldDevice) -> dict[str, Any]:
    metadata = getattr(device, "config", None) or {}
    if not metadata:
        return {}

    # Device mode describes server/request-level behavior. Tag mode remains
    # per-tag write behavior and is intentionally not serialized here.
    config: dict[str, Any] = {"metadata": metadata}
    mode = metadata.get("mode")
    if mode:
        config["mode"] = mode
    if "response_delay_ms" in metadata:
        config["response_delay_ms"] = metadata["response_delay_ms"]
    return config


def tag_config(tag: FieldTag) -> dict[str, Any]:
    config = {
        "name": tag.name,
        "node_id": tag.node_id,
        "browse_name": tag.browse_name,
        "opc_item_path": tag.opc_item_path,
        "data_type": tag.data_type,
        "update_rate_ms": tag.update_rate_ms,
        "simulation_type": tag.simulation_type,
        "min_value": tag.min_value,
        "max_value": tag.max_value,
        "variance": tag.variance,
        "initial_value": tag.initial_value,
    }
    config.update(tag_behavior_config(tag))
    return config


def tag_behavior_config(tag: FieldTag) -> dict[str, Any]:
    metadata = getattr(tag, "config", None) or {}
    if not metadata:
        return {}

    config: dict[str, Any] = {"metadata": metadata}
    behavior = metadata.get("behavior")
    if behavior:
        config["behavior"] = behavior
    if "mode_config" in metadata:
        config["mode_config"] = metadata["mode_config"]
    return config


def ignition_tag_config(tag: FieldTag, opc_server: str, tag_name: str | None = None) -> dict[str, Any]:
    return {
        "name": tag_name or tag.name,
        "tagType": "AtomicTag",
        "valueSource": "opc",
        "dataType": tag.ignition_data_type,
        "opcServer": opc_server,
        "opcItemPath": tag.node_id,
    }


def ignition_folder_config(folder_name: str, tags: list[FieldTag], opc_server: str) -> dict[str, Any]:
    return {
        "name": folder_name,
        "tagType": "Folder",
        "tags": [ignition_tag_config(tag, opc_server) for tag in tags],
    }
