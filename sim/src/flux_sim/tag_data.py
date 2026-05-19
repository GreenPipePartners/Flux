from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from flux_sim.addressing import parse_address


@dataclass(frozen=True)
class DeviceInventoryEntry:
    name: str
    driver: str
    status: str = ""
    detail: str = ""

    @property
    def strategy_key(self) -> str:
        return strategy_key_for_driver(self.driver)


@dataclass(frozen=True)
class ProviderTagReference:
    path: str
    tag_type: str
    data_type: str = ""
    value_source: str = ""
    opc_server: str = ""
    opc_item_path: str = ""
    device_name: str = ""


@dataclass(frozen=True)
class DeviceTagBinding:
    provider_name: str
    device_name: str
    driver: str
    strategy_key: str
    source_path: str
    tag_name: str
    tag_type: str
    data_type: str
    value_source: str
    opc_server: str
    opc_item_path: str
    address: dict[str, str]


@dataclass(frozen=True)
class ProviderDeviceProfile:
    device: DeviceInventoryEntry
    tag_count: int = 0
    data_type_counts: Counter[str] = field(default_factory=Counter)
    value_source_counts: Counter[str] = field(default_factory=Counter)
    unmatched_tag_count: int = 0


@dataclass(frozen=True)
class TagDataCatalog:
    provider_name: str
    devices: dict[str, DeviceInventoryEntry]
    tag_references: list[ProviderTagReference]

    @property
    def referenced_device_names(self) -> set[str]:
        return {self.resolved_device_name(tag) for tag in self.tag_references if self.resolved_device_name(tag)}

    @property
    def unreferenced_device_names(self) -> set[str]:
        return set(self.devices) - self.referenced_device_names

    @property
    def unknown_device_names(self) -> set[str]:
        return {tag.device_name for tag in self.tag_references if tag.device_name and self.resolved_device_name(tag) not in self.devices}

    @property
    def collector_device(self) -> DeviceInventoryEntry | None:
        collectors = [device for device in self.devices.values() if device.strategy_key == "acm"]
        return collectors[0] if len(collectors) == 1 else None

    def resolved_device_name(self, tag: ProviderTagReference) -> str:
        if tag.device_name in self.devices:
            return tag.device_name
        collector = self.collector_device
        return collector.name if collector is not None and tag.device_name else tag.device_name

    def device_profiles(self) -> list[ProviderDeviceProfile]:
        tags_by_device: dict[str, list[ProviderTagReference]] = {}
        for tag in self.tag_references:
            device_name = self.resolved_device_name(tag)
            if device_name:
                tags_by_device.setdefault(device_name, []).append(tag)

        profiles = []
        for device_name, device in sorted(self.devices.items()):
            tags = tags_by_device.get(device_name, [])
            profiles.append(
                ProviderDeviceProfile(
                    device=device,
                    tag_count=len(tags),
                    data_type_counts=Counter(tag.data_type for tag in tags if tag.data_type),
                    value_source_counts=Counter(tag.value_source for tag in tags if tag.value_source),
                )
            )
        return profiles

    def device_tag_bindings(self) -> list[DeviceTagBinding]:
        return list(iter_device_tag_bindings(self))


def load_tag_data_catalog(
    provider_name: str,
    *,
    devices_path: str | Path,
    tags_path: str | Path,
) -> TagDataCatalog:
    devices = parse_device_inventory(Path(devices_path).read_text(encoding="utf-8"))
    payload = json.loads(Path(tags_path).read_text(encoding="utf-8"))
    return tag_data_catalog_from_payload(provider_name, devices=devices, payload=payload)


def tag_data_catalog_from_payload(
    provider_name: str,
    *,
    devices: Iterable[DeviceInventoryEntry],
    payload: dict[str, Any],
) -> TagDataCatalog:
    return TagDataCatalog(
        provider_name=provider_name,
        devices={device.name: device for device in devices if device.name},
        tag_references=list(iter_provider_tag_references(payload)),
    )


def iter_device_tag_bindings(catalog: TagDataCatalog) -> Iterable[DeviceTagBinding]:
    for reference in catalog.tag_references:
        device_name = catalog.resolved_device_name(reference)
        if not device_name:
            continue
        device = catalog.devices.get(device_name)
        if device is None:
            continue
        yield DeviceTagBinding(
            provider_name=catalog.provider_name,
            device_name=device.name,
            driver=device.driver,
            strategy_key=device.strategy_key,
            source_path=reference.path,
            tag_name=tag_name_for_path(reference.path),
            tag_type=reference.tag_type,
            data_type=reference.data_type,
            value_source=reference.value_source,
            opc_server=reference.opc_server,
            opc_item_path=reference.opc_item_path,
            address=parse_address(device.strategy_key, reference.opc_item_path),
        )


def tag_name_for_path(path: str) -> str:
    return path.rsplit("/", 1)[-1] if path else ""


def parse_device_inventory(content: str) -> list[DeviceInventoryEntry]:
    entries: list[DeviceInventoryEntry] = []
    pending: DeviceInventoryEntry | None = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower() == "details":
            continue
        columns = [column.strip() for column in raw_line.split("\t")]
        if len(columns) < 2 or not columns[0] or not columns[1]:
            if pending is not None:
                pending = DeviceInventoryEntry(pending.name, pending.driver, pending.status, line)
                entries[-1] = pending
            continue
        pending = DeviceInventoryEntry(
            name=columns[0],
            driver=columns[1],
            status=columns[2] if len(columns) > 2 else "",
            detail=columns[3] if len(columns) > 3 else "",
        )
        entries.append(pending)
    return entries


def iter_provider_tag_references(root: dict[str, Any]) -> Iterable[ProviderTagReference]:
    stack: list[tuple[dict[str, Any], str, dict[str, Any]]] = [(root, "", {})]
    while stack:
        node, path, inherited_parameters = stack.pop()
        name = str(node.get("name") or "")
        node_path = join_tag_path(path, name)
        parameters = merged_parameters(inherited_parameters, node.get("parameters"))
        tag_type = str(node.get("tagType") or "")
        value_source = scalar_string(node.get("valueSource"))
        opc_item_path = scalar_string(node.get("opcItemPath"))
        device_name = device_name_for_node(node, parameters)
        if tag_type == "AtomicTag":
            yield ProviderTagReference(
                path=node_path,
                tag_type=tag_type,
                data_type=scalar_string(node.get("dataType")),
                value_source=value_source,
                opc_server=scalar_string(node.get("opcServer")),
                opc_item_path=opc_item_path,
                device_name=device_name,
            )
        for child in reversed([child for child in node.get("tags") or [] if isinstance(child, dict)]):
            stack.append((child, node_path, parameters))


def device_name_for_node(node: dict[str, Any], parameters: dict[str, Any]) -> str:
    for key in ("OPC_Device", "OPCDevice", "Device", "device"):
        value = parameter_value(parameters.get(key))
        if value:
            return value
    opc_item_path = scalar_string(node.get("opcItemPath"))
    match = re.search(r";s=([^\.\[]+)", opc_item_path)
    return match.group(1) if match else ""


def merged_parameters(inherited: dict[str, Any], local: Any) -> dict[str, Any]:
    result = dict(inherited)
    if isinstance(local, dict):
        result.update(local)
    return result


def parameter_value(value: Any) -> str:
    if isinstance(value, dict):
        return scalar_string(value.get("value"))
    return scalar_string(value)


def strategy_key_for_driver(driver: str) -> str:
    normalized = driver.lower().replace(" ", "")
    if "logix" in normalized:
        return "logix"
    if "modbus" in normalized:
        return "modbus"
    if "opcua" in normalized or "serverclient" in normalized:
        return "acm"
    if normalized.startswith("s7"):
        return "siemens"
    return "generic"


def scalar_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def join_tag_path(parent_path: str, name: str) -> str:
    if not parent_path:
        return name
    if not name:
        return parent_path
    return f"{parent_path}/{name}"
