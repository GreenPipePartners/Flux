from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flux.base.field_config import single_device_endpoint_config
from flux.field.ignition import (
    FieldIgnitionConfiguration,
    configure_field_agent_ignition,
    opc_tag_configs,
)
from flux.sim.models import DeviceConfig


IMPORTANT_TAG_FIELDS = (
    "path",
    "name",
    "dataType",
    "valueSource",
    "opcServer",
    "opcItemPath",
)


@dataclass(frozen=True)
class IgnitionTagExportCompareResult:
    configuration: FieldIgnitionConfiguration
    source_tags: list[dict[str, Any]]
    exported_tags: list[dict[str, Any]]
    differences: list[str]

    @property
    def matches(self) -> bool:
        return not self.differences


def configure_export_compare_field_device_ignition(
    fx: Any,
    device: DeviceConfig,
    *,
    tag_provider: str = "default",
    tag_folder: str | None = None,
    endpoint_url: str | None = None,
    connection_name: str | None = None,
    cleanup_existing: bool = True,
    collision_policy: str = "o",
) -> IgnitionTagExportCompareResult:
    config = {"endpoints": [single_device_endpoint_config(device, endpoint_url=endpoint_url)]}
    return configure_export_compare_field_agent_ignition(
        fx,
        config,
        tag_provider=tag_provider,
        tag_folder=tag_folder or device.base_device.name,
        connection_names=[connection_name] if connection_name else None,
        cleanup_existing=cleanup_existing,
        collision_policy=collision_policy,
    )


def configure_export_compare_field_agent_ignition(
    fx: Any,
    config: dict[str, Any],
    *,
    tag_provider: str = "default",
    tag_folder: str = "FieldAgent",
    connection_names: list[str] | None = None,
    cleanup_existing: bool = True,
    collision_policy: str = "o",
) -> IgnitionTagExportCompareResult:
    configuration = configure_field_agent_ignition(
        fx,
        config,
        tag_provider=tag_provider,
        tag_folder=tag_folder,
        connection_names=connection_names,
        cleanup_existing=cleanup_existing,
        collision_policy=collision_policy,
    )
    source_payload = source_ignition_payload(
        config,
        tag_folder=configuration.tag_folder,
        connection_names=configuration.connection_names,
    )
    export_result = fx.tag.export_tags(
        "%s%s" % (configuration.tag_base_path, configuration.tag_folder), recursive=True
    )
    exported_payload = export_result.tags

    source_tags = normalize_ignition_tag_configs(source_payload)
    exported_tags = normalize_ignition_tag_configs(exported_payload)
    return IgnitionTagExportCompareResult(
        configuration=configuration,
        source_tags=source_tags,
        exported_tags=exported_tags,
        differences=compare_ignition_tag_configs(source_tags, exported_tags),
    )


def source_ignition_payload(
    config: dict[str, Any], *, tag_folder: str, connection_names: list[str]
) -> dict[str, Any]:
    endpoints = list(config.get("endpoints") or [])
    if len(endpoints) != len(connection_names):
        raise ValueError("connection_names must match the number of FieldAgent endpoints")

    tags: list[dict[str, Any]] = []
    for endpoint, connection_name in zip(endpoints, connection_names, strict=True):
        tags.extend(opc_tag_configs(endpoint, connection_name))
    return {"name": tag_folder, "tagType": "Folder", "tags": tags}


def normalize_ignition_tag_configs(payload: Any) -> list[dict[str, Any]]:
    roots = payload if isinstance(payload, list) else [payload]
    rows: list[dict[str, Any]] = []
    for root in roots:
        collect_atomic_tag_configs(root, parent_path="", rows=rows)
    return sorted(rows, key=lambda row: row["path"])


def collect_atomic_tag_configs(
    node: Any, *, parent_path: str, rows: list[dict[str, Any]]
) -> None:
    if not isinstance(node, dict):
        return

    name = str(node.get("name") or "")
    path = "/".join(part for part in (parent_path, name) if part)
    if node.get("tagType") == "AtomicTag":
        row = {field: normalize_tag_value(node.get(field)) for field in IMPORTANT_TAG_FIELDS}
        row["name"] = name
        row["path"] = path
        rows.append(row)

    for child in node.get("tags") or []:
        collect_atomic_tag_configs(child, parent_path=path, rows=rows)


def normalize_tag_value(value: Any) -> Any:
    return "" if value is None else value


def compare_ignition_tag_configs(
    source_tags: list[dict[str, Any]], exported_tags: list[dict[str, Any]]
) -> list[str]:
    source_by_path = {tag["path"]: tag for tag in source_tags}
    exported_by_path = {tag["path"]: tag for tag in exported_tags}
    differences: list[str] = []

    for path in sorted(set(source_by_path) - set(exported_by_path)):
        differences.append("missing exported tag: %s" % path)
    for path in sorted(set(exported_by_path) - set(source_by_path)):
        differences.append("unexpected exported tag: %s" % path)
    for path in sorted(set(source_by_path) & set(exported_by_path)):
        source = source_by_path[path]
        exported = exported_by_path[path]
        for field in IMPORTANT_TAG_FIELDS:
            if source[field] != exported[field]:
                differences.append(
                    "%s %s mismatch: source=%r exported=%r"
                    % (path, field, source[field], exported[field])
                )
    return differences
