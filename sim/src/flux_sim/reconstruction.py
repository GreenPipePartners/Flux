from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ImportedTagNode:
    path: str
    name: str
    tag_type: str
    data_type: str = ""
    value_source: str = ""
    type_id: str = ""
    opc_server: str = ""
    opc_item_path: str = ""
    source_tag_path: str = ""
    parameters: Any = None
    value: Any = None
    raw_config: dict[str, Any] = field(default_factory=dict)
    children: tuple["ImportedTagNode", ...] = ()

    def to_tag_config(self) -> dict[str, Any]:
        config = dict(self.raw_config)
        config.setdefault("name", self.name)
        config.setdefault("tagType", self.tag_type)
        _set_if_present(config, "dataType", self.data_type)
        _set_if_present(config, "valueSource", self.value_source)
        _set_if_present(config, "typeId", self.type_id)
        _set_if_present(config, "opcServer", self.opc_server)
        _set_if_present(config, "opcItemPath", self.opc_item_path)
        _set_if_present(config, "sourceTagPath", self.source_tag_path)
        if self.parameters is not None:
            config.setdefault("parameters", self.parameters)
        if self.value is not None:
            config.setdefault("value", self.value)
        if self.children:
            config["tags"] = [child.to_tag_config() for child in self.children]
        return {key: value for key, value in config.items() if value is not None}


@dataclass(frozen=True)
class ImportedProviderTree:
    provider_name: str
    root: ImportedTagNode

    @property
    def tags(self) -> tuple[dict[str, Any], ...]:
        return tuple(child.to_tag_config() for child in self.root.children)

    def to_tag_config(self) -> dict[str, Any]:
        return self.root.to_tag_config()


@dataclass(frozen=True)
class SimTagDefinition:
    path: str
    tag_type: str
    data_type: str = ""
    value_source: str = ""
    value: Any = None
    opc_server: str = ""
    opc_item_path: str = ""
    expression: str = ""


@dataclass(frozen=True)
class SimProviderModel:
    provider_name: str
    tags: tuple[SimTagDefinition, ...]
    requests: tuple[Any, ...] = ()
    udt_type_index: dict[str, Any] = field(default_factory=dict)


class ExpressionInterface(Protocol):
    def flatten_tag_requests(self, tags: Any) -> tuple[Any, ...]: ...

    def build_udt_type_index(self, tags: Any) -> dict[str, Any]: ...

    def extract_expression_references(self, expression: str) -> tuple[str, ...]: ...

    def resolve_parameter_binding(self, template: str, context: Any) -> Any: ...


def load_imported_provider_tree(database_path: str | Path, provider_name: str) -> ImportedProviderTree:
    with sqlite3.connect(Path(database_path)) as connection:
        connection.row_factory = sqlite3.Row
        provider = connection.execute(
            "SELECT id, name FROM sim_provider WHERE name = ?",
            (provider_name,),
        ).fetchone()
        if provider is None:
            raise ValueError(f"Provider not found: {provider_name}")
        rows = connection.execute(
            """
            SELECT id, parent_id, path, name, tag_type, data_type, value_source, type_id,
                opc_server, opc_item_path, source_tag_path, parameters_json, value_json, raw_config_json
            FROM sim_imported_tag
            WHERE provider_id = ?
            ORDER BY depth, sort_order, id
            """,
            (provider["id"],),
        ).fetchall()

    if not rows:
        raise ValueError(f"Provider has no imported tags: {provider_name}")
    children_by_parent: dict[int | None, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        children_by_parent[row["parent_id"]].append(row)
    root = next((row for row in rows if row["parent_id"] is None), rows[0])
    return ImportedProviderTree(
        provider_name=str(provider["name"]),
        root=_build_node(root, children_by_parent),
    )


def build_sim_provider_model(
    provider_tree: ImportedProviderTree,
    *,
    expression_interface: ExpressionInterface | None = None,
) -> SimProviderModel:
    tag_configs = provider_tree.tags
    requests: tuple[Any, ...] = ()
    udt_type_index: dict[str, Any] = {}
    if expression_interface is not None:
        requests = expression_interface.flatten_tag_requests(tag_configs)
        udt_type_index = expression_interface.build_udt_type_index(tag_configs)
    return SimProviderModel(
        provider_name=provider_tree.provider_name,
        tags=tuple(iter_sim_tag_definitions(provider_tree.root)),
        requests=requests,
        udt_type_index=udt_type_index,
    )


def iter_sim_tag_definitions(root: ImportedTagNode) -> tuple[SimTagDefinition, ...]:
    definitions: list[SimTagDefinition] = []

    def walk(node: ImportedTagNode) -> None:
        if node.path:
            definitions.append(
                SimTagDefinition(
                    path=node.path,
                    tag_type=node.tag_type,
                    data_type=node.data_type,
                    value_source=node.value_source,
                    value=node.value,
                    opc_server=node.opc_server,
                    opc_item_path=node.opc_item_path,
                    expression=str(node.raw_config.get("expression") or ""),
                )
            )
        for child in node.children:
            walk(child)

    walk(root)
    return tuple(definitions)


def load_ignition_expression_interface() -> ExpressionInterface:
    from fluxy.ignition_expression.bindings import resolve_parameter_binding
    from fluxy.ignition_expression.requests import (
        build_udt_type_index,
        extract_expression_references,
        flatten_tag_requests,
    )

    class IgnitionExpressionInterface:
        pass

    IgnitionExpressionInterface.flatten_tag_requests = staticmethod(flatten_tag_requests)
    IgnitionExpressionInterface.build_udt_type_index = staticmethod(build_udt_type_index)
    IgnitionExpressionInterface.extract_expression_references = staticmethod(extract_expression_references)
    IgnitionExpressionInterface.resolve_parameter_binding = staticmethod(resolve_parameter_binding)

    return IgnitionExpressionInterface()


def _build_node(row: sqlite3.Row, children_by_parent: dict[int | None, list[sqlite3.Row]]) -> ImportedTagNode:
    child_rows = children_by_parent.get(row["id"], [])
    return ImportedTagNode(
        path=str(row["path"]),
        name=str(row["name"]),
        tag_type=str(row["tag_type"]),
        data_type=str(row["data_type"]),
        value_source=str(row["value_source"]),
        type_id=str(row["type_id"]),
        opc_server=str(row["opc_server"]),
        opc_item_path=str(row["opc_item_path"]),
        source_tag_path=str(row["source_tag_path"]),
        parameters=_loads_json(row["parameters_json"]),
        value=_loads_json(row["value_json"]),
        raw_config=_loads_json(row["raw_config_json"]) or {},
        children=tuple(_build_node(child, children_by_parent) for child in child_rows),
    )


def _loads_json(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def _set_if_present(config: dict[str, Any], key: str, value: str) -> None:
    if value:
        config.setdefault(key, value)
