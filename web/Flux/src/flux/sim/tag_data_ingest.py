from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.db import transaction

from flux.base.models import SimDevice, SimDeviceTag, SimDriver, SimServer, TagNode, TagProvider
from flux.base.services import import_provider_payload
from flux_sim.tag_data import DeviceInventoryEntry, DeviceTagBinding, parse_device_inventory, tag_data_catalog_from_payload


INGEST_BATCH_SIZE = 5000
DEFAULT_SIM_SERVER_NAME = "Flux sim OPC-UA Server"
IGNITION_OPC_SERVER_NAMES = {
    "ignition opc ua server",
    "ignition opc-ua server",
}


@dataclass(frozen=True)
class TagDataIngestResult:
    provider: TagProvider
    device_count: int
    tag_count: int
    unknown_device_count: int
    unreferenced_device_count: int


def ingest_tag_data_catalog(
    *,
    provider_name: str,
    devices_path: str | Path,
    tags_path: str | Path,
    keep_raw_config: bool = True,
) -> TagDataIngestResult:
    tags_source = Path(tags_path)
    payload = json.loads(tags_source.read_text(encoding="utf-8"))
    devices = parse_device_inventory(Path(devices_path).read_text(encoding="utf-8"))
    return ingest_tag_data_catalog_payload(
        provider_name=provider_name,
        payload=payload,
        devices=devices,
        source=TagProvider.Source.JSON_UPLOAD,
        source_name=str(tags_source),
        keep_raw_config=keep_raw_config,
    )


def ingest_live_tag_data_catalog(
    fx: Any,
    *,
    source_provider: str,
    provider_name: str | None = None,
    keep_raw_config: bool = True,
) -> TagDataIngestResult:
    result = fx.tag.export_tags(f"[{source_provider}]", recursive=True)
    payload = result.tags
    if not isinstance(payload, dict):
        payload = json.loads(result.raw_json)
    return ingest_tag_data_catalog_payload(
        provider_name=provider_name or source_provider,
        payload=payload,
        devices=devices_from_fluxy(fx.device.list_devices()),
        source=TagProvider.Source.IGNITION_PROVIDER,
        source_name=source_provider,
        keep_raw_config=keep_raw_config,
    )


def ingest_tag_data_catalog_payload(
    *,
    provider_name: str,
    payload: dict[str, Any],
    devices: list[DeviceInventoryEntry],
    source: str,
    source_name: str,
    keep_raw_config: bool = True,
) -> TagDataIngestResult:
    catalog = tag_data_catalog_from_payload(provider_name, devices=devices, payload=payload)
    with transaction.atomic():
        import_result = import_provider_payload(
            payload,
            provider_name=provider_name,
            source=source,
            source_name=source_name,
            keep_raw_config=keep_raw_config,
        )
        bindings = catalog.device_tag_bindings()
        import_result.provider.sim_server = infer_sim_server(bindings)
        import_result.provider.save(update_fields=["sim_server"])
        devices_by_name: dict[str, SimDevice] = {}
        for device in catalog.devices.values():
            driver = upsert_driver(device.driver, device.strategy_key)
            sim_device, _created = SimDevice.objects.update_or_create(
                provider=import_result.provider,
                name=device.name,
                defaults={
                    "driver": driver,
                    "source_status": device.status,
                    "source_detail": device.detail,
                    "config": {"source_driver": device.driver, "strategy_key": device.strategy_key},
                    "enabled": True,
                },
            )
            devices_by_name[device.name] = sim_device

        source_paths = bulk_upsert_device_tags(import_result.provider, devices_by_name, bindings)

        delete_stale_device_tags(import_result.provider, source_paths)

    return TagDataIngestResult(
        provider=import_result.provider,
        device_count=len(catalog.devices),
        tag_count=len(source_paths),
        unknown_device_count=len(catalog.unknown_device_names),
        unreferenced_device_count=len(catalog.unreferenced_device_names),
    )


def infer_sim_server(bindings: list[DeviceTagBinding]) -> SimServer:
    opc_server = predominant_opc_server(bindings)
    if not opc_server or normalized_opc_server_name(opc_server) in IGNITION_OPC_SERVER_NAMES:
        return default_sim_server()
    return SimServer.objects.get_or_create(
        name=sim_server_name(opc_server),
        defaults={
            "endpoint_url": "opc.tcp://0.0.0.0:4840/flux/sim/%s" % safe_name(opc_server),
            "application_uri": "urn:flux:sim:%s" % safe_name(opc_server).lower(),
            "product_uri": "urn:flux:sim",
            "namespace_uri": "urn:flux:sim:%s" % safe_name(opc_server).lower(),
            "enabled": True,
            "security_policy": "None",
            "description": "Inferred from imported opcServer=%s" % opc_server,
        },
    )[0]


def predominant_opc_server(bindings: list[DeviceTagBinding]) -> str:
    counts: dict[str, int] = {}
    for binding in bindings:
        if binding.opc_server:
            counts[binding.opc_server] = counts.get(binding.opc_server, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def default_sim_server() -> SimServer:
    return SimServer.objects.get_or_create(
        name=DEFAULT_SIM_SERVER_NAME,
        defaults={
            "endpoint_url": "opc.tcp://0.0.0.0:4840/flux/sim",
            "application_uri": "urn:flux:sim",
            "product_uri": "urn:flux:sim",
            "namespace_uri": "urn:flux:sim",
            "enabled": True,
            "security_policy": "None",
        },
    )[0]


def sim_server_name(opc_server: str) -> str:
    return "Flux sim %s Server" % opc_server.strip()


def normalized_opc_server_name(opc_server: str) -> str:
    return " ".join(opc_server.lower().replace("_", " ").split())


def safe_name(value: str) -> str:
    cleaned = "".join(character if character.isalnum() or character in "-_" else "_" for character in value.strip())
    return cleaned or "server"


def devices_from_fluxy(devices: list[Any]) -> list[DeviceInventoryEntry]:
    return [
        DeviceInventoryEntry(
            name=str(getattr(device, "name", "") or ""),
            driver=str(getattr(device, "driver", "") or "Unknown"),
            status=str(getattr(device, "state", "") or ""),
            detail=fluxy_device_detail(device),
        )
        for device in devices
        if getattr(device, "name", "")
    ]


def fluxy_device_detail(device: Any) -> str:
    payload = getattr(device, "payload", None)
    if isinstance(payload, dict):
        for key in ("description", "Description", "detail", "Detail"):
            value = payload.get(key)
            if value:
                return str(value)
    enabled = getattr(device, "enabled", None)
    return "enabled=%s" % enabled if enabled is not None else ""


def upsert_driver(driver_name: str, strategy_key: str) -> SimDriver:
    key = driver_name.strip().lower().replace(" ", "_") or "unknown"
    driver, _created = SimDriver.objects.update_or_create(
        key=key,
        defaults={
            "label": driver_name or "Unknown",
            "strategy_key": strategy_key,
            "ignition_driver_names": [driver_name] if driver_name else [],
        },
    )
    return driver


def bulk_upsert_device_tags(
    provider: TagProvider,
    devices_by_name: dict[str, SimDevice],
    bindings: list[DeviceTagBinding],
) -> list[str]:
    source_paths = [binding.source_path for binding in bindings]
    tag_nodes = {
        node.path: node
        for batch in chunked(source_paths, INGEST_BATCH_SIZE)
        for node in TagNode.objects.filter(provider=provider, path__in=batch)
    }
    for batch in chunked(bindings, INGEST_BATCH_SIZE):
        SimDeviceTag.objects.bulk_create(
            [device_tag(provider, devices_by_name, tag_nodes, binding) for binding in batch],
            update_conflicts=True,
            unique_fields=["provider", "source_path"],
            update_fields=[
                "device",
                "tag_node",
                "tag_name",
                "data_type",
                "value_source",
                "opc_server",
                "opc_item_path",
                "address_strategy",
                "address",
                "enabled",
            ],
        )
    return source_paths


def delete_stale_device_tags(provider: TagProvider, source_paths: list[str]) -> None:
    if not source_paths:
        SimDeviceTag.objects.filter(provider=provider).delete()
        return

    current_source_paths = set(source_paths)
    stale_ids = [
        device_tag_id
        for device_tag_id, source_path in SimDeviceTag.objects.filter(provider=provider).values_list(
            "id", "source_path"
        )
        if source_path not in current_source_paths
    ]
    for batch in chunked(stale_ids, INGEST_BATCH_SIZE):
        SimDeviceTag.objects.filter(id__in=batch).delete()


def device_tag(
    provider: TagProvider,
    devices_by_name: dict[str, SimDevice],
    tag_nodes: dict[str, TagNode],
    binding: DeviceTagBinding,
) -> SimDeviceTag:
    return SimDeviceTag(
        provider=provider,
        source_path=binding.source_path,
        device=devices_by_name[binding.device_name],
        tag_node=tag_nodes.get(binding.source_path),
        tag_name=binding.tag_name,
        data_type=binding.data_type,
        value_source=binding.value_source,
        opc_server=binding.opc_server,
        opc_item_path=binding.opc_item_path,
        address_strategy=binding.strategy_key,
        address=binding.address,
        enabled=True,
    )


def chunked[T](items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
