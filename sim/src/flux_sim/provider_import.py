from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


STRUCTURAL_KEYS = {"tags"}


@dataclass(frozen=True)
class ProviderImportResult:
    provider_name: str
    source_path: Path
    source_sha256: str
    counts: Counter[str]

    @property
    def total_nodes(self) -> int:
        return sum(self.counts.values())


def import_provider_export(
    source_path: str | Path,
    database_path: str | Path,
    *,
    provider_name: str,
    batch_size: int = 1000,
    keep_raw_config: bool = True,
) -> ProviderImportResult:
    source = Path(source_path)
    database = Path(database_path)
    source_hash = sha256_file(source)
    with source.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("Ignition tag provider export must be a JSON object")
    if payload.get("tagType") != "Provider":
        raise ValueError("Ignition tag provider export root must have tagType='Provider'")

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        create_schema(connection)
        counts = replace_provider_rows(
            connection,
            payload,
            provider_name=provider_name,
            source_path=source,
            source_sha256=source_hash,
            batch_size=batch_size,
            keep_raw_config=keep_raw_config,
        )
    return ProviderImportResult(
        provider_name=provider_name,
        source_path=source,
        source_sha256=source_hash,
        counts=counts,
    )


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS sim_provider (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            source_name TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            root_tag_type TEXT NOT NULL DEFAULT 'Provider',
            total_nodes INTEGER NOT NULL DEFAULT 0,
            folder_count INTEGER NOT NULL DEFAULT 0,
            atomic_tag_count INTEGER NOT NULL DEFAULT 0,
            udt_instance_count INTEGER NOT NULL DEFAULT 0,
            udt_type_count INTEGER NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sim_imported_tag (
            id INTEGER PRIMARY KEY,
            provider_id INTEGER NOT NULL REFERENCES sim_provider(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES sim_imported_tag(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            tag_type TEXT NOT NULL,
            data_type TEXT NOT NULL DEFAULT '',
            value_source TEXT NOT NULL DEFAULT '',
            type_id TEXT NOT NULL DEFAULT '',
            opc_server TEXT NOT NULL DEFAULT '',
            opc_item_path TEXT NOT NULL DEFAULT '',
            source_tag_path TEXT NOT NULL DEFAULT '',
            depth INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            has_children INTEGER NOT NULL DEFAULT 0,
            parameters_json TEXT,
            value_json TEXT,
            raw_config_json TEXT,
            UNIQUE(provider_id, path)
        );

        CREATE INDEX IF NOT EXISTS idx_sim_imported_tag_provider_type
            ON sim_imported_tag(provider_id, tag_type);
        CREATE INDEX IF NOT EXISTS idx_sim_imported_tag_provider_value_source
            ON sim_imported_tag(provider_id, value_source);
        CREATE INDEX IF NOT EXISTS idx_sim_imported_tag_provider_data_type
            ON sim_imported_tag(provider_id, data_type);
        CREATE INDEX IF NOT EXISTS idx_sim_imported_tag_provider_parent
            ON sim_imported_tag(provider_id, parent_id);
        """
    )


def replace_provider_rows(
    connection: sqlite3.Connection,
    root: dict[str, Any],
    *,
    provider_name: str,
    source_path: Path,
    source_sha256: str,
    batch_size: int,
    keep_raw_config: bool,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    connection.execute(
        """
        INSERT INTO sim_provider (name, source_name, source_path, source_sha256, root_tag_type)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            source_name = excluded.source_name,
            source_path = excluded.source_path,
            source_sha256 = excluded.source_sha256,
            root_tag_type = excluded.root_tag_type,
            imported_at = CURRENT_TIMESTAMP
        """,
        (
            provider_name,
            str(root.get("name") or ""),
            str(source_path),
            source_sha256,
            str(root.get("tagType") or "Provider"),
        ),
    )
    provider_id = int(
        connection.execute("SELECT id FROM sim_provider WHERE name = ?", (provider_name,)).fetchone()[0]
    )
    connection.execute("DELETE FROM sim_imported_tag WHERE provider_id = ?", (provider_id,))

    pending: list[tuple[Any, ...]] = []
    path_to_id: dict[str, int] = {}
    for row in iter_tag_rows(root, keep_raw_config=keep_raw_config):
        parent_path = row.pop("parent_path")
        if parent_path not in path_to_id and pending:
            flush_rows(connection, pending, path_to_id)
        parent_id = path_to_id.get(parent_path)
        counts[row["tag_type"]] += 1
        pending.append(row_tuple(provider_id, parent_id, row))
        if len(pending) >= batch_size:
            flush_rows(connection, pending, path_to_id)
    flush_rows(connection, pending, path_to_id)

    connection.execute(
        """
        UPDATE sim_provider
        SET total_nodes = ?, folder_count = ?, atomic_tag_count = ?, udt_instance_count = ?, udt_type_count = ?
        WHERE id = ?
        """,
        (
            sum(counts.values()),
            counts.get("Folder", 0),
            counts.get("AtomicTag", 0),
            counts.get("UdtInstance", 0),
            counts.get("UdtType", 0),
            provider_id,
        ),
    )
    return counts


def iter_tag_rows(root: dict[str, Any], *, keep_raw_config: bool = True) -> Iterable[dict[str, Any]]:
    stack: list[tuple[dict[str, Any], str, int, int, str]] = [(root, "", 0, 0, "")]
    while stack:
        node, parent_path, depth, sort_order, path = stack.pop()
        children = [child for child in node.get("tags") or [] if isinstance(child, dict)]
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
            "depth": depth,
            "sort_order": sort_order,
            "has_children": bool(children),
            "parameters": node.get("parameters"),
            "value": node.get("value"),
            "raw_config": compact_raw_config(node) if keep_raw_config else None,
        }
        for child_sort_order, child in reversed(list(enumerate(children))):
            child_name = str(child.get("name") or "")
            stack.append((child, path, depth + 1, child_sort_order, join_tag_path(path, child_name)))


def flush_rows(
    connection: sqlite3.Connection,
    pending: list[tuple[Any, ...]],
    path_to_id: dict[str, int],
) -> None:
    if not pending:
        return
    connection.executemany(
        """
        INSERT INTO sim_imported_tag (
            provider_id, parent_id, path, name, tag_type, data_type, value_source, type_id,
            opc_server, opc_item_path, source_tag_path, depth, sort_order, has_children,
            parameters_json, value_json, raw_config_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        pending,
    )
    for row in pending:
        row_id = int(
            connection.execute(
                "SELECT id FROM sim_imported_tag WHERE provider_id = ? AND path = ?",
                (row[0], row[2]),
            ).fetchone()[0]
        )
        path_to_id[row[2]] = row_id
    pending.clear()


def row_tuple(provider_id: int, parent_id: int | None, row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        provider_id,
        parent_id,
        row["path"],
        row["name"],
        row["tag_type"],
        row["data_type"],
        row["value_source"],
        row["type_id"],
        row["opc_server"],
        row["opc_item_path"],
        row["source_tag_path"],
        row["depth"],
        row["sort_order"],
        int(row["has_children"]),
        json_dumps_or_none(row["parameters"]),
        json_dumps_or_none(row["value"]),
        json_dumps_or_none(row["raw_config"]),
    )


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


def json_dumps_or_none(value: Any) -> str | None:
    return None if value is None else json.dumps(value, separators=(",", ":"), sort_keys=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
