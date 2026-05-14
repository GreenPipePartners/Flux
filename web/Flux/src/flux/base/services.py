from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.db import transaction

from .models import TagNode, TagProvider, TagSelection


STRUCTURAL_KEYS = {"tags"}


@dataclass(frozen=True)
class ImportResult:
    provider: TagProvider
    counts: Counter[str]

    @property
    def total_nodes(self) -> int:
        return sum(self.counts.values())


@dataclass
class TagTreeNode:
    name: str
    path: str
    tag_type: str
    children: dict[str, "TagTreeNode"] = field(default_factory=dict)
    selected: bool = False
    partial: bool = False

    @property
    def children_list(self) -> list["TagTreeNode"]:
        return sorted(self.children.values(), key=lambda child: child.name.lower())

    @property
    def icon(self) -> str:
        if self.tag_type == "UdtInstance":
            return "◆"
        if self.tag_type == "AtomicTag":
            return "●"
        return "📁"


@dataclass(frozen=True)
class TagProviderTree:
    provider: TagProvider
    nodes: list[TagTreeNode]
    selected_count: int


def import_provider_payload(
    payload: dict[str, Any],
    *,
    provider_name: str,
    source: str,
    source_name: str = "",
    keep_raw_config: bool = True,
) -> ImportResult:
    if not isinstance(payload, dict):
        raise ValueError("Ignition tag provider export must be a JSON object")
    if payload.get("tagType") != "Provider":
        raise ValueError("Ignition tag provider export root must have tagType='Provider'")

    normalized_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    source_sha256 = hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()

    with transaction.atomic():
        provider, _created = TagProvider.objects.update_or_create(
            name=provider_name,
            defaults={
                "source": source,
                "source_name": source_name or str(payload.get("name") or ""),
                "source_sha256": source_sha256,
                "root_tag_type": str(payload.get("tagType") or "Provider"),
            },
        )
        TagNode.objects.filter(provider=provider).delete()

        counts: Counter[str] = Counter()
        rows = list(iter_tag_rows(payload, keep_raw_config=keep_raw_config))
        path_to_node: dict[str, TagNode] = {}
        for row in rows:
            counts[row["tag_type"]] += 1

        for depth in sorted({int(row["depth"]) for row in rows}):
            pending: list[TagNode] = []
            for row in [row for row in rows if int(row["depth"]) == depth]:
                parent = path_to_node.get(row.pop("parent_path"))
                pending.append(TagNode(provider=provider, parent=parent, **row))
            created_nodes = TagNode.objects.bulk_create(pending)
            for node in created_nodes:
                path_to_node[node.path] = node

        provider.total_nodes = sum(counts.values())
        provider.folder_count = counts.get("Folder", 0)
        provider.atomic_tag_count = counts.get("AtomicTag", 0)
        provider.udt_instance_count = counts.get("UdtInstance", 0)
        provider.udt_type_count = counts.get("UdtType", 0)
        provider.save(
            update_fields=[
                "total_nodes",
                "folder_count",
                "atomic_tag_count",
                "udt_instance_count",
                "udt_type_count",
                "imported_at",
            ]
        )

    return ImportResult(provider=provider, counts=counts)


def import_provider_json_bytes(
    content: bytes,
    *,
    provider_name: str,
    source_name: str = "",
    keep_raw_config: bool = True,
) -> ImportResult:
    payload = json.loads(content.decode("utf-8"))
    return import_provider_payload(
        payload,
        provider_name=provider_name,
        source=TagProvider.Source.JSON_UPLOAD,
        source_name=source_name,
        keep_raw_config=keep_raw_config,
    )


def import_provider_from_fluxy(
    fx: Any,
    *,
    source_provider: str,
    provider_name: str | None = None,
    keep_raw_config: bool = True,
) -> ImportResult:
    result = fx.tag.export_tags(f"[{source_provider}]", recursive=True)
    payload = result.tags
    if not isinstance(payload, dict):
        payload = json.loads(result.raw_json)
    return import_provider_payload(
        payload,
        provider_name=provider_name or source_provider,
        source=TagProvider.Source.IGNITION_PROVIDER,
        source_name=source_provider,
        keep_raw_config=keep_raw_config,
    )


def iter_tag_rows(root: dict[str, Any], *, keep_raw_config: bool = True) -> Iterable[dict[str, Any]]:
    stack: list[tuple[dict[str, Any], str, int, int, str]] = [(root, "", 0, 0, "")]
    while stack:
        node, parent_path, depth, sort_order, path = stack.pop()
        children = [child for child in node.get("tags") or [] if isinstance(child, dict)]
        raw_config = compact_raw_config(node) if keep_raw_config else {}
        yield {
            "parent_path": parent_path,
            "path": path,
            "name": str(node.get("name") or ""),
            "tag_type": str(node.get("tagType") or ""),
            "data_type": scalar_string(node.get("dataType")),
            "value_source": scalar_string(node.get("valueSource")),
            "type_id": scalar_string(node.get("typeId")),
            "opc_server": scalar_string(node.get("opcServer")),
            "opc_item_path": scalar_string(node.get("opcItemPath")),
            "source_tag_path": scalar_string(node.get("sourceTagPath")),
            "expression": scalar_string(node.get("expression")),
            "engineering_units": scalar_string(node.get("engUnit")) or scalar_string(node.get("engineeringUnits")),
            "documentation": scalar_string(node.get("documentation")),
            "tooltip": scalar_string(node.get("tooltip")),
            "parameters": node.get("parameters"),
            "value": node.get("value"),
            "raw_config": raw_config,
            "depth": depth,
            "sort_order": sort_order,
            "has_children": bool(children),
        }
        for child_sort_order, child in reversed(list(enumerate(children))):
            child_name = str(child.get("name") or "")
            stack.append((child, path, depth + 1, child_sort_order, join_tag_path(path, child_name)))


def provider_names() -> list[str]:
    return list(TagProvider.objects.order_by("name").values_list("name", flat=True))


def build_provider_tree(provider_name: str, *, purpose: str = TagSelection.Purpose.SIM, max_depth: int = 8) -> TagProviderTree | None:
    if not provider_name:
        return None
    provider = TagProvider.objects.filter(name=provider_name).first()
    if provider is None:
        return None
    selected_paths = set(
        TagSelection.objects.filter(provider=provider, purpose=purpose, enabled=True).values_list("path", flat=True)
    )
    nodes_by_path: dict[str, TagTreeNode] = {}
    roots: dict[str, TagTreeNode] = {}
    rows = TagNode.objects.filter(provider=provider, depth__gt=0, depth__lte=max_depth).order_by("depth", "sort_order", "id")
    for row in rows:
        path = row.path
        if path == "_types_" or path.startswith("_types_/"):
            continue
        if row.tag_type == "AtomicTag" and has_udt_instance_ancestor(path, nodes_by_path):
            continue
        node = TagTreeNode(
            name=row.name,
            path=path,
            tag_type=row.tag_type,
            selected=path in selected_paths,
            partial=path not in selected_paths and any(selected.startswith(path + "/") for selected in selected_paths),
        )
        nodes_by_path[path] = node
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent_path and parent_path in nodes_by_path:
            nodes_by_path[parent_path].children[node.name] = node
        else:
            roots[node.name] = node
    return TagProviderTree(provider=provider, nodes=sorted(roots.values(), key=lambda node: node.name.lower()), selected_count=len(selected_paths))


def set_selection(provider_name: str, path: str, *, purpose: str = TagSelection.Purpose.SIM, enabled: bool) -> int:
    provider = TagProvider.objects.get(name=provider_name)
    cleaned_path = path.strip("/")
    if enabled:
        TagSelection.objects.update_or_create(
            provider=provider,
            purpose=purpose,
            path=cleaned_path,
            defaults={"enabled": True},
        )
    else:
        TagSelection.objects.filter(provider=provider, purpose=purpose, path=cleaned_path).delete()
    return 1


def replace_selection(provider_name: str, paths: list[str], *, purpose: str = TagSelection.Purpose.SIM) -> int:
    provider = TagProvider.objects.get(name=provider_name)
    cleaned_paths = sorted({path.strip("/") for path in paths if path.strip("/")})
    TagSelection.objects.filter(provider=provider, purpose=purpose).delete()
    TagSelection.objects.bulk_create(
        [TagSelection(provider=provider, purpose=purpose, path=path, enabled=True) for path in cleaned_paths],
        ignore_conflicts=True,
    )
    return len(cleaned_paths)


def selected_source_paths(provider_name: str, *, purpose: str = TagSelection.Purpose.SIM) -> list[str]:
    provider = TagProvider.objects.filter(name=provider_name).first()
    if provider is None:
        return []
    selected_prefixes = list(
        TagSelection.objects.filter(provider=provider, purpose=purpose, enabled=True).values_list("path", flat=True)
    )
    if not selected_prefixes:
        return []
    rows = TagNode.objects.filter(provider=provider, value_source="opc").exclude(path="")
    return sorted(
        {
            row.path
            for row in rows
            if any(row.path == prefix or row.path.startswith(prefix.rstrip("/") + "/") for prefix in selected_prefixes)
        }
    )


def has_udt_instance_ancestor(path: str, nodes_by_path: dict[str, TagTreeNode]) -> bool:
    parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
    while parent_path:
        parent = nodes_by_path.get(parent_path)
        if parent and parent.tag_type == "UdtInstance":
            return True
        parent_path = parent_path.rsplit("/", 1)[0] if "/" in parent_path else ""
    return False


def compact_raw_config(node: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in node.items() if key not in STRUCTURAL_KEYS}


def join_tag_path(parent_path: str, name: str) -> str:
    if not parent_path:
        return name
    if not name:
        return parent_path
    return f"{parent_path}/{name}"


def scalar_string(value: Any) -> str:
    return value if isinstance(value, str) else ""
