from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from django.db import transaction
from django.db.models import Q

from flux.sim.models import TagNode, TagProvider, TagSelection


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
    data_type: str = ""
    value_source: str = ""
    expression: str = ""
    source_tag_path: str = ""
    value: Any = None
    children: dict[str, "TagTreeNode"] = field(default_factory=dict)
    selected: bool = False
    partial: bool = False
    expandable: bool = False
    node_id: int | None = None
    simulation_mode: str = "estimate_live"
    simulation_config: dict[str, Any] = field(default_factory=dict)

    @property
    def children_list(self) -> list["TagTreeNode"]:
        return sorted(self.children.values(), key=lambda child: child.name.lower())

    @property
    def icon(self) -> str:
        if self.tag_type == "UdtInstance":
            return "◆"
        if self.tag_type == "AtomicTag":
            return data_type_icon(self.data_type, self.value)
        return "📁"

    @property
    def simulation_eligible(self) -> bool:
        return self.tag_type == "AtomicTag" and normalized_value_source(self.value_source) == "opc"

    @property
    def source_badge_text(self) -> str:
        if self.tag_type != "AtomicTag" or self.simulation_eligible:
            return ""
        return "|".join(source_badges(self.value_source, self.expression, self.source_tag_path))


@dataclass(frozen=True)
class TagProviderTree:
    provider: TagProvider
    nodes: list[TagTreeNode]
    selected_count: int


@dataclass(frozen=True)
class TagTreeRenderContext:
    selections: list[TagSelection]
    fully_selected_paths: set[str]
    metadata_by_path: dict[str, dict[str, Any]]


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
    selections = list(TagSelection.objects.filter(provider=provider, purpose=purpose))
    nodes_by_path: dict[str, TagTreeNode] = {}
    roots: dict[str, TagTreeNode] = {}
    rows = [
        row
        for row in TagNode.objects.filter(provider=provider, depth__gt=0, depth__lte=max_depth).order_by(
            "depth", "sort_order", "id"
        )
        if row.path != "_types_" and not row.path.startswith("_types_/")
    ]
    context = tree_render_context(provider, rows, selections)
    for row in rows:
        path = row.path
        node = tree_node_from_row(row, context)
        nodes_by_path[path] = node
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent_path and parent_path in nodes_by_path:
            nodes_by_path[parent_path].children[node.name] = node
        else:
            roots[node.name] = node
    return TagProviderTree(
        provider=provider,
        nodes=sorted(roots.values(), key=lambda node: node.name.lower()),
        selected_count=sum(1 for selection in selections if selection.enabled),
    )


def provider_tree_children(provider_name: str, parent_path: str = "", *, purpose: str = TagSelection.Purpose.SIM) -> TagProviderTree | None:
    if not provider_name:
        return None
    provider = TagProvider.objects.filter(name=provider_name).first()
    if provider is None:
        return None
    selections = list(TagSelection.objects.filter(provider=provider, purpose=purpose))
    parent = TagNode.objects.filter(provider=provider, path=parent_path.strip("/")).first()
    if parent is None:
        return TagProviderTree(provider=provider, nodes=[], selected_count=sum(1 for selection in selections if selection.enabled))
    rows = list(
        TagNode.objects.filter(provider=provider, parent=parent)
        .exclude(path="")
        .exclude(path="_types_")
        .exclude(path__startswith="_types_/")
        .only(
            "id",
            "name",
            "path",
            "tag_type",
            "data_type",
            "value_source",
            "expression",
            "source_tag_path",
            "value",
            "has_children",
        )
        .order_by("sort_order", "id")
    )
    rows = [row for row in rows if not skip_lazy_tree_row(row)]
    context = tree_render_context(provider, rows, selections)
    nodes = [tree_node_from_row(row, context) for row in rows]
    return TagProviderTree(provider=provider, nodes=nodes, selected_count=sum(1 for selection in selections if selection.enabled))


def selected_branch_rows(provider_name: str, *, purpose: str = TagSelection.Purpose.SIM, limit: int = 250) -> list[str]:
    provider = TagProvider.objects.filter(name=provider_name).first()
    if provider is None:
        return []
    return list(
        TagSelection.objects.filter(provider=provider, purpose=purpose, enabled=True)
        .order_by("path")
        .values_list("path", flat=True)[:limit]
    )


def search_provider_tree(provider_name: str, query: str, *, purpose: str = TagSelection.Purpose.SIM, limit: int = 50) -> TagProviderTree | None:
    cleaned = query.strip()
    if not provider_name or not cleaned:
        return provider_tree_children(provider_name, "", purpose=purpose)
    provider = TagProvider.objects.filter(name=provider_name).first()
    if provider is None:
        return None
    selections = list(TagSelection.objects.filter(provider=provider, purpose=purpose))
    rows = list(
        TagNode.objects.filter(provider=provider)
        .exclude(path="")
        .exclude(path="_types_")
        .exclude(path__startswith="_types_/")
        .filter(path__icontains=cleaned)
        .only(
            "id",
            "name",
            "path",
            "tag_type",
            "data_type",
            "value_source",
            "expression",
            "source_tag_path",
            "value",
            "has_children",
        )
        .order_by("depth", "sort_order", "id")[:limit]
    )
    context = tree_render_context(provider, rows, selections)
    return TagProviderTree(
        provider=provider,
        nodes=[tree_node_from_row(row, context) for row in rows],
        selected_count=sum(1 for selection in selections if selection.enabled),
    )


def tree_render_context(provider: TagProvider, rows: list[TagNode], selections: list[TagSelection]) -> TagTreeRenderContext:
    return TagTreeRenderContext(
        selections=selections,
        fully_selected_paths=selected_subtree_paths(provider.id, rows, selections),
        metadata_by_path=tree_node_metadata_by_path(provider.id, rows),
    )


def tree_node_from_row(row: TagNode, context: TagTreeRenderContext) -> TagTreeNode:
    selected = subtree_fully_selected(row, context)
    metadata = tree_node_metadata(row, context)
    return TagTreeNode(
        node_id=row.id,
        name=row.name,
        path=row.path,
        tag_type=row.tag_type,
        data_type=metadata["data_type"],
        value_source=metadata["value_source"],
        expression=metadata["expression"],
        source_tag_path=metadata["source_tag_path"],
        value=metadata["value"],
        selected=selected,
        partial=path_partially_selected(row.path, context.selections, selected),
        expandable=row.has_children,
        simulation_mode=exact_atomic_selection_mode(row, context.selections),
        simulation_config=exact_atomic_selection_config(row, context.selections),
    )


def tree_node_metadata(row: TagNode, context: TagTreeRenderContext | None = None) -> dict[str, Any]:
    if context is not None:
        return context.metadata_by_path.get(row.path) or direct_tree_node_metadata(row)
    return inherited_tree_node_metadata(row)


def direct_tree_node_metadata(row: TagNode) -> dict[str, Any]:
    return {
        "data_type": row.data_type,
        "value_source": row.value_source,
        "expression": row.expression,
        "source_tag_path": row.source_tag_path,
        "value": row.value,
    }


def inherited_tree_node_metadata(row: TagNode) -> dict[str, Any]:
    data_type = row.data_type
    value_source = row.value_source
    expression = row.expression
    source_tag_path = row.source_tag_path
    value = row.value
    inherited = inherited_udt_definition_node(row) if row.tag_type == "AtomicTag" else None
    if inherited is not None:
        data_type = data_type or inherited.data_type
        value_source = value_source or inherited.value_source
        expression = expression or inherited.expression
        source_tag_path = source_tag_path or inherited.source_tag_path
        value = value if value is not None else inherited.value
    return {
        "data_type": data_type,
        "value_source": value_source,
        "expression": expression,
        "source_tag_path": source_tag_path,
        "value": value,
    }


def tree_node_metadata_by_path(provider_id: int, rows: list[TagNode]) -> dict[str, dict[str, Any]]:
    metadata_by_path = {row.path: direct_tree_node_metadata(row) for row in rows}
    atomic_rows = [row for row in rows if row.tag_type == "AtomicTag"]
    if not atomic_rows:
        return metadata_by_path

    ancestor_paths = sorted({ancestor for row in atomic_rows for ancestor in path_ancestors(row.path)})
    if not ancestor_paths:
        return metadata_by_path
    udt_ancestors = list(
        TagNode.objects.filter(provider_id=provider_id, path__in=ancestor_paths, tag_type="UdtInstance").only(
            "path", "type_id"
        )
    )
    udt_by_path = {node.path: node for node in udt_ancestors}
    inherited_path_by_row_path: dict[str, str] = {}
    for row in atomic_rows:
        udt_path = nearest_path_prefix(row.path, udt_by_path.keys())
        if not udt_path:
            continue
        type_path = tag_type_definition_path(udt_by_path[udt_path].type_id)
        relative_path = row.path.removeprefix(udt_path).strip("/")
        if type_path and relative_path:
            inherited_path_by_row_path[row.path] = f"{type_path}/{relative_path}"
    if not inherited_path_by_row_path:
        return metadata_by_path

    inherited_nodes = {
        node.path: node
        for node in TagNode.objects.filter(provider_id=provider_id, path__in=set(inherited_path_by_row_path.values())).only(
            "path",
            "data_type",
            "value_source",
            "expression",
            "source_tag_path",
            "value",
        )
    }
    for row in atomic_rows:
        inherited = inherited_nodes.get(inherited_path_by_row_path.get(row.path, ""))
        if inherited is None:
            continue
        metadata = metadata_by_path[row.path]
        metadata_by_path[row.path] = {
            "data_type": metadata["data_type"] or inherited.data_type,
            "value_source": metadata["value_source"] or inherited.value_source,
            "expression": metadata["expression"] or inherited.expression,
            "source_tag_path": metadata["source_tag_path"] or inherited.source_tag_path,
            "value": metadata["value"] if metadata["value"] is not None else inherited.value,
        }
    return metadata_by_path


def nearest_path_prefix(path: str, prefixes) -> str:
    matches = [prefix for prefix in prefixes if path.startswith(prefix + "/")]
    return max(matches, key=len) if matches else ""


def inherited_udt_definition_node(row: TagNode) -> TagNode | None:
    udt_ancestor = nearest_udt_instance_ancestor(row)
    if udt_ancestor is None or not udt_ancestor.type_id:
        return None
    type_path = tag_type_definition_path(udt_ancestor.type_id)
    if not type_path:
        return None
    relative_path = row.path.removeprefix(udt_ancestor.path).strip("/")
    if not relative_path:
        return None
    return TagNode.objects.filter(provider_id=row.provider_id, path=f"{type_path}/{relative_path}").first()


def nearest_udt_instance_ancestor(row: TagNode) -> TagNode | None:
    parent = row.parent
    while parent is not None:
        if parent.tag_type == "UdtInstance":
            return parent
        parent = parent.parent
    return None


def tag_type_definition_path(type_id: str) -> str:
    path = type_id.strip()
    if "]" in path:
        path = path.split("]", 1)[1]
    if path and not path.startswith("_types_/") and path != "_types_":
        path = f"_types_/{path}"
    return path.strip("/")


def path_effectively_selected(path: str, selections: list[TagSelection]) -> bool:
    matches = [selection for selection in selections if path == selection.path or path.startswith(selection.path + "/")]
    if not matches:
        return False
    return max(matches, key=lambda selection: len(selection.path)).enabled


def path_partially_selected(path: str, selections: list[TagSelection], selected: bool) -> bool:
    has_selected_child = any(selection.enabled and selection.path.startswith(path + "/") for selection in selections)
    has_excluded_child = any(not selection.enabled and selection.path.startswith(path + "/") for selection in selections)
    if selected:
        return has_excluded_child
    return has_selected_child


def subtree_fully_selected(row: TagNode, context: TagTreeRenderContext) -> bool:
    if path_effectively_selected(row.path, context.selections):
        return True
    return row.path in context.fully_selected_paths


def selected_subtree_paths(provider_id: int, rows: list[TagNode], selections: list[TagSelection]) -> set[str]:
    roots = [
        row.path
        for row in rows
        if not path_effectively_selected(row.path, selections)
        and any(selection.enabled and selection.path.startswith(row.path + "/") for selection in selections)
    ]
    if not roots:
        return set()
    query = Q()
    for root in roots:
        query |= Q(path=root) | Q(path__startswith=f"{root}/")
    descendants = list(
        TagNode.objects.filter(provider_id=provider_id)
        .filter(query)
        .exclude(path="_types_")
        .exclude(path__startswith="_types_/")
        .values("id", "path", "parent_id")
    )
    path_by_id = {row["id"]: row["path"] for row in descendants}
    children_by_parent: dict[int, list[int]] = {}
    for row in descendants:
        parent_id = row["parent_id"]
        if parent_id is not None and parent_id in path_by_id:
            children_by_parent.setdefault(parent_id, []).append(row["id"])

    selected_paths: set[str] = set()
    for row in sorted(descendants, key=lambda item: item["path"].count("/"), reverse=True):
        path = row["path"]
        child_ids = children_by_parent.get(row["id"], [])
        if path_effectively_selected(path, selections) or (child_ids and all(path_by_id[child_id] in selected_paths for child_id in child_ids)):
            selected_paths.add(path)
    return selected_paths


def effective_selection_mode(path: str, selections: list[TagSelection]) -> str:
    matches = [
        selection
        for selection in selections
        if selection.enabled and (path == selection.path or path.startswith(selection.path + "/"))
    ]
    if not matches:
        return "estimate_live"
    config = max(matches, key=lambda selection: len(selection.path)).config or {}
    return str(config.get("simulation_mode") or "estimate_live")


def effective_selection_config(path: str, selections: list[TagSelection]) -> dict[str, Any]:
    matches = [
        selection
        for selection in selections
        if selection.enabled and (path == selection.path or path.startswith(selection.path + "/"))
    ]
    if not matches:
        return {"simulation_mode": "estimate_live"}
    return dict(max(matches, key=lambda selection: len(selection.path)).config or {})


def exact_atomic_selection_mode(row: TagNode, selections: list[TagSelection]) -> str:
    config = exact_atomic_selection_config(row, selections)
    return str(config.get("simulation_mode") or "")


def exact_atomic_selection_config(row: TagNode, selections: list[TagSelection]) -> dict[str, Any]:
    if row.tag_type != "AtomicTag":
        return {}
    selection = next(
        (selection for selection in selections if selection.enabled and selection.path == row.path),
        None,
    )
    return dict(selection.config or {}) if selection is not None else {}


def data_type_icon(data_type: str, value: Any = None) -> str:
    normalized = data_type.lower()
    if "bool" in normalized:
        return "TF"
    if "float8" in normalized or "double" in normalized:
        return "F8"
    if "float" in normalized:
        return "F4"
    if "int8" in normalized:
        return "I8"
    if "int4" in normalized:
        return "I4"
    if "int2" in normalized:
        return "I2"
    if "int1" in normalized:
        return "I1"
    if "int" in normalized:
        return "I?"
    if "datetime" in normalized or "date" in normalized:
        return "DT"
    if "dataset" in normalized:
        return "DS"
    if "string" in normalized:
        return 'S"'
    if isinstance(value, bool):
        return "TF"
    if isinstance(value, int):
        return "I4"
    if isinstance(value, float):
        return "F8"
    if isinstance(value, str) and value.strip().startswith('{"columns"'):
        return "DS"
    if isinstance(value, str) and value:
        return 'S"'
    return "??"


def normalized_value_source(value_source: str) -> str:
    return str(value_source or "").strip().lower()


def source_badges(value_source: str, expression: str = "", source_tag_path: str = "") -> list[str]:
    normalized = normalized_value_source(value_source)
    badges: list[str] = []
    if normalized == "reference" or source_tag_path:
        badges.append("Ref")
    elif normalized == "expression":
        badges.append("Expr")
    else:
        badges.append("Memory")
    if expression and "Expr" not in badges:
        badges.append("Expr")
    return badges


def node_is_opc_backed(row: TagNode) -> bool:
    metadata = tree_node_metadata(row)
    return normalized_value_source(metadata["value_source"]) == "opc"


def skip_lazy_tree_row(row: TagNode) -> bool:
    return row.tag_type == "AtomicTag" and row.path.rsplit("/", 1)[0].endswith("_types_")


def set_selection(provider_name: str, path: str, *, purpose: str = TagSelection.Purpose.SIM, enabled: bool, config: dict | None = None) -> int:
    provider = TagProvider.objects.get(name=provider_name)
    cleaned_path = path.strip("/")
    if enabled:
        TagSelection.objects.update_or_create(
            provider=provider,
            purpose=purpose,
            path=cleaned_path,
            defaults={"enabled": True, "config": config or {}},
        )
        TagSelection.objects.filter(provider=provider, purpose=purpose, enabled=False, path=cleaned_path).delete()
        TagSelection.objects.filter(provider=provider, purpose=purpose, enabled=False, path__startswith=f"{cleaned_path}/").delete()
    else:
        ancestor_paths = path_ancestors(cleaned_path)
        has_enabled_ancestor = TagSelection.objects.filter(
            provider=provider, purpose=purpose, enabled=True, path__in=ancestor_paths
        ).exists()
        if has_enabled_ancestor:
            TagSelection.objects.update_or_create(
                provider=provider,
                purpose=purpose,
                path=cleaned_path,
                defaults={"enabled": False, "config": {}},
            )
        else:
            TagSelection.objects.filter(provider=provider, purpose=purpose).filter(
                Q(path=cleaned_path) | Q(path__startswith=f"{cleaned_path}/")
            ).delete()
    return 1


def path_ancestors(path: str) -> list[str]:
    parts = [part for part in path.split("/") if part]
    return ["/".join(parts[:index]) for index in range(1, len(parts))]


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
    selections = list(TagSelection.objects.filter(provider=provider, purpose=purpose))
    if not any(selection.enabled for selection in selections):
        return []
    rows = (
        TagNode.objects.filter(provider=provider, tag_type="AtomicTag")
        .exclude(path="")
        .exclude(path="_types_")
        .exclude(path__startswith="_types_/")
    )
    return sorted(
        {
            row.path
            for row in rows
            if path_effectively_selected(row.path, selections) and node_is_opc_backed(row)
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
