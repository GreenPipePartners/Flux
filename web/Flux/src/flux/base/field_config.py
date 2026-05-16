from __future__ import annotations

from typing import Any

from .models import FieldDevice, FieldEndpoint, FieldTag


def enabled_endpoint_configs() -> list[dict[str, Any]]:
    endpoints = FieldEndpoint.objects.filter(enabled=True).prefetch_related("devices__tags")
    return [endpoint_config(endpoint) for endpoint in endpoints]


def endpoint_config(endpoint: FieldEndpoint) -> dict[str, Any]:
    devices = FieldDevice.objects.filter(endpoint=endpoint, enabled=True).prefetch_related("tags")
    return {
        "name": endpoint.name,
        "endpoint_url": endpoint.endpoint_url,
        "application_uri": endpoint.application_uri,
        "product_uri": endpoint.product_uri,
        "namespace_uri": endpoint.namespace_uri,
        "security_policy": endpoint.security_policy,
        "devices": [device_config(device) for device in devices],
    }


def device_config(device: FieldDevice) -> dict[str, Any]:
    tags = device.tags.filter(enabled=True).order_by("name")
    return {
        "name": device.name,
        "device_type": device.device_type,
        "browse_path": device.browse_path,
        "tags": [tag_config(tag) for tag in tags],
    }


def tag_config(tag: FieldTag) -> dict[str, Any]:
    return {
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
