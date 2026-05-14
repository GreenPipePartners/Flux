from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from flux_sim.reconstruction import (
    build_sim_provider_model,
    load_ignition_expression_interface,
    load_imported_provider_tree,
)

from .models import SimProviderSelection


@dataclass
class ImportedTreeNode:
    name: str
    path: str
    tag_type: str
    children: dict[str, "ImportedTreeNode"] = field(default_factory=dict)
    selected: bool = False
    partial: bool = False

    @property
    def children_list(self) -> list["ImportedTreeNode"]:
        return sorted(self.children.values(), key=lambda child: child.name.lower())

    @property
    def icon(self) -> str:
        if self.tag_type == "UdtInstance":
            return "◆"
        if self.tag_type == "AtomicTag":
            return "●"
        return "📁"


@dataclass(frozen=True)
class ImportedProviderTree:
    provider: str
    nodes: list[ImportedTreeNode]
    selected_count: int


def default_sim_database_path() -> Path:
    return settings.BASE_DIR.parents[1] / "sim" / "flux-sim.db"


def imported_provider_names(database_path: Path | None = None) -> list[str]:
    database = database_path or default_sim_database_path()
    if not database.exists():
        return []
    with sqlite3.connect(database) as connection:
        return [
            str(row[0])
            for row in connection.execute("SELECT name FROM sim_provider ORDER BY name").fetchall()
        ]


def build_imported_provider_tree(
    provider: str,
    *,
    database_path: Path | None = None,
    max_depth: int = 8,
) -> ImportedProviderTree | None:
    database = database_path or default_sim_database_path()
    if not provider or not database.exists():
        return None
    selected_paths = set(
        SimProviderSelection.objects.filter(provider=provider, enabled=True).values_list("path", flat=True)
    )
    nodes_by_path: dict[str, ImportedTreeNode] = {}
    roots: dict[str, ImportedTreeNode] = {}
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT path, name, tag_type, depth
            FROM sim_imported_tag
            WHERE provider_id = (SELECT id FROM sim_provider WHERE name = ?)
                AND path != ''
                AND path NOT LIKE '_types_/%'
                AND path != '_types_'
                AND depth <= ?
            ORDER BY depth, sort_order, id
            """,
            (provider, max_depth),
        ).fetchall()
    for row in rows:
        path = str(row["path"])
        if row["tag_type"] == "AtomicTag" and has_udt_instance_ancestor(path, nodes_by_path):
            continue
        node = ImportedTreeNode(
            name=str(row["name"]),
            path=path,
            tag_type=str(row["tag_type"]),
            selected=path in selected_paths,
            partial=path not in selected_paths
            and any(selected.startswith(path + "/") for selected in selected_paths),
        )
        nodes_by_path[path] = node
        parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
        if parent_path and parent_path in nodes_by_path:
            nodes_by_path[parent_path].children[node.name] = node
        else:
            roots[node.name] = node
    return ImportedProviderTree(
        provider=provider,
        nodes=sorted(roots.values(), key=lambda node: node.name.lower()),
        selected_count=len(selected_paths),
    )


def has_udt_instance_ancestor(path: str, nodes_by_path: dict[str, ImportedTreeNode]) -> bool:
    parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
    while parent_path:
        parent = nodes_by_path.get(parent_path)
        if parent and parent.tag_type == "UdtInstance":
            return True
        parent_path = parent_path.rsplit("/", 1)[0] if "/" in parent_path else ""
    return False


def set_imported_selection(provider: str, path: str, *, enabled: bool) -> int:
    if enabled:
        SimProviderSelection.objects.update_or_create(
            provider=provider,
            path=path.strip("/"),
            defaults={"enabled": True},
        )
    else:
        SimProviderSelection.objects.filter(provider=provider, path=path.strip("/")).delete()
    return 1


def replace_imported_selection(provider: str, paths: list[str]) -> int:
    cleaned_paths = sorted({path.strip("/") for path in paths if path.strip("/")})
    SimProviderSelection.objects.filter(provider=provider).delete()
    SimProviderSelection.objects.bulk_create(
        [SimProviderSelection(provider=provider, path=path, enabled=True) for path in cleaned_paths],
        ignore_conflicts=True,
    )
    return len(cleaned_paths)


def selected_source_paths(provider: str, *, database_path: Path | None = None) -> list[str]:
    database = database_path or default_sim_database_path()
    selected_prefixes = list(
        SimProviderSelection.objects.filter(provider=provider, enabled=True).values_list("path", flat=True)
    )
    if not selected_prefixes or not database.exists():
        return []
    tree = load_imported_provider_tree(database, provider)
    model = build_sim_provider_model(tree, expression_interface=load_ignition_expression_interface())
    paths = []
    for request in model.requests:
        if getattr(request, "value_source", "") != "opc" or not getattr(request, "resolved", True):
            continue
        tag_path = str(getattr(request, "tag_path", "") or "")
        if any(tag_path == prefix or tag_path.startswith(prefix.rstrip("/") + "/") for prefix in selected_prefixes):
            paths.append(tag_path)
    return sorted(set(paths))
