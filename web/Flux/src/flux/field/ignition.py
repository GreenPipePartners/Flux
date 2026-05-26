from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flux.base.field_config import single_device_endpoint_config
from flux.sim.models import DeviceConfig


@dataclass(frozen=True)
class FieldIgnitionConfiguration:
    connection_names: list[str]
    tag_base_path: str
    tag_folder: str
    tag_count: int


def configure_field_device_ignition(
    fx: Any,
    device: DeviceConfig,
    *,
    tag_provider: str = "default",
    tag_folder: str | None = None,
    endpoint_url: str | None = None,
    connection_name: str | None = None,
    cleanup_existing: bool = True,
    collision_policy: str = "o",
) -> FieldIgnitionConfiguration:
    config = {"endpoints": [single_device_endpoint_config(device, endpoint_url=endpoint_url)]}
    return configure_field_agent_ignition(
        fx,
        config,
        tag_provider=tag_provider,
        tag_folder=tag_folder or safe_name(device.base_device.name),
        connection_names=[connection_name] if connection_name else None,
        cleanup_existing=cleanup_existing,
        collision_policy=collision_policy,
    )


def configure_field_agent_ignition(
    fx: Any,
    config: dict[str, Any],
    *,
    tag_provider: str = "default",
    tag_folder: str = "FieldAgent",
    connection_names: list[str] | None = None,
    cleanup_existing: bool = True,
    collision_policy: str = "o",
) -> FieldIgnitionConfiguration:
    endpoints = list(config.get("endpoints") or [])
    selected_connection_names = connection_names or [
        opcua_connection_name(endpoint.get("name", "field")) for endpoint in endpoints
    ]
    if len(selected_connection_names) != len(endpoints):
        raise ValueError("connection_names must match the number of FieldAgent endpoints")

    tag_base_path = tag_base_path_for_provider(tag_provider)
    if cleanup_existing:
        cleanup_field_agent_ignition(
            fx,
            tag_provider=tag_provider,
            tag_folder=tag_folder,
            connection_names=selected_connection_names,
        )

    tag_configs: list[dict[str, Any]] = []
    for endpoint, connection_name in zip(endpoints, selected_connection_names, strict=True):
        endpoint_url = str(endpoint["endpoint_url"])
        security_policy = str(endpoint.get("security_policy") or "None")
        fx.opcua.add_connection(
            connection_name,
            "Flux FieldAgent OPC UA simulator",
            endpoint_url,
            endpoint_url,
            security_policy=security_policy,
            security_mode="None",
            settings=opcua_connection_settings(endpoint_url, security_policy=security_policy),
        )
        tag_configs.extend(opc_tag_configs(endpoint, connection_name))

    if tag_configs:
        fx.tag.configure(
            [
                {
                    "name": tag_folder,
                    "tagType": "Folder",
                    "tags": tag_configs,
                }
            ],
            base_path=tag_base_path,
            collision_policy=collision_policy,
        )

    return FieldIgnitionConfiguration(
        connection_names=selected_connection_names,
        tag_base_path=tag_base_path,
        tag_folder=tag_folder,
        tag_count=len(tag_configs),
    )


def cleanup_field_agent_ignition(
    fx: Any,
    *,
    tag_provider: str = "default",
    tag_folder: str = "FieldAgent",
    connection_names: list[str] | None = None,
) -> None:
    try:
        fx.tag.delete_tags("%s%s" % (tag_base_path_for_provider(tag_provider), tag_folder))
    except Exception:
        pass

    for connection_name in connection_names or []:
        try:
            fx.opcua.remove_connection(connection_name)
        except Exception:
            pass


def opc_tag_configs(endpoint: dict[str, Any], connection_name: str) -> list[dict[str, Any]]:
    tag_configs: list[dict[str, Any]] = []
    for device in endpoint.get("devices") or []:
        device_name = str(device["name"])
        for tag in device.get("tags") or []:
            tag_configs.append(
                {
                    "name": "%s_%s" % (safe_name(device_name), safe_name(str(tag["name"]))),
                    "tagType": "AtomicTag",
                    "valueSource": "opc",
                    "dataType": ignition_data_type(str(tag["data_type"])),
                    "opcServer": connection_name,
                    "opcItemPath": str(tag["node_id"]),
                }
            )
    return tag_configs


def opcua_connection_settings(endpoint_url: str, *, security_policy: str = "None") -> dict[str, Any]:
    return {
        "ENABLED": True,
        "DISCOVERYURL": endpoint_url,
        "ENDPOINTURL": endpoint_url,
        "SECURITYPOLICY": security_policy,
        "SECURITYMODE": "None",
        "CERTIFICATEVALIDATIONENABLED": False,
        "CONNECTTIMEOUT": 5000,
        "ACKNOWLEDGETIMEOUT": 5000,
        "REQUESTTIMEOUT": 5000,
        "SESSIONTIMEOUT": 60000,
    }


def opcua_connection_name(endpoint_name: str) -> str:
    return "Flux Field %s" % safe_name(endpoint_name)


def tag_base_path_for_provider(tag_provider: str) -> str:
    if tag_provider.startswith("[") and tag_provider.endswith("]"):
        return tag_provider
    return "[%s]" % tag_provider


def ignition_data_type(data_type: str) -> str:
    return {
        "bool": "Boolean",
        "int": "Int4",
        "float": "Float8",
        "string": "String",
    }[data_type]


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
