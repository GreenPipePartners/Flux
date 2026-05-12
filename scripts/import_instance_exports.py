#!/usr/bin/env python3
"""Build a SQLite database from Ignition tag dataset and equipment exports.

The expected inputs are:
- tags.txt: output from dataset_cap.py, containing repeated blocks of
  Tag/Quality/Timestamp/Dataset Contents.
- equipment.txt: a 19-column CSV export without a header.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DATASET_COLUMNS = [
    "TagName",
    "TagDescription",
    "DataType",
    "Overview",
    "Detail",
    "Summary",
    "Setpoint",
]

EQUIPMENT_COLUMNS = [
    "name",
    "tag_path",
    "equipment_type",
    "equipment_type_source_id",
    "subtype",
    "subtype_source_id",
    "field_name",
    "route_name",
    "site_name",
    "field_id",
    "route_id",
    "site_id",
    "equipment_id",
    "model_code",
    "device_reference",
    "gathering_system",
    "merrick_id",
    "controller_name",
    "equipment_index",
]


@dataclass
class DatasetBlock:
    source_tag: str
    subtype: str
    quality: str
    timestamp_text: str
    headers: list[str]
    rows: list[dict[str, str | None]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tags", type=Path, default=Path("tags.txt"))
    parser.add_argument("--equipment", type=Path, default=Path("equipment.txt"))
    parser.add_argument("--db", type=Path, default=Path("instance_exports.sqlite3"))
    parser.add_argument(
        "--preserve",
        action="store_true",
        help="Keep existing tables and append rows instead of rebuilding them.",
    )
    parser.add_argument(
        "--equipment-map-column",
        choices=("auto", "subtype", "equipment_type"),
        default="auto",
        help=(
            "Equipment column used to map to tag_subtypes. "
            "auto tries subtype first, then equipment_type."
        ),
    )
    return parser.parse_args()


def clean_cell(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value.lower() == "null":
        return None
    return value


def bool_cell(value: str | None) -> int | None:
    value = clean_cell(value)
    if value is None or value == "":
        return None
    if value.lower() == "true":
        return 1
    if value.lower() == "false":
        return 0
    raise ValueError(f"Expected boolean cell, got {value!r}")


def subtype_from_tag(source_tag: str) -> str:
    return source_tag.rsplit("/", 1)[-1].strip()


def parse_tags(path: Path) -> list[DatasetBlock]:
    blocks: list[DatasetBlock] = []
    source_tag = ""
    quality = ""
    timestamp_text = ""
    headers: list[str] = []
    rows: list[dict[str, str | None]] = []
    in_dataset = False

    def flush() -> None:
        nonlocal source_tag, quality, timestamp_text, headers, rows, in_dataset
        if source_tag:
            blocks.append(
                DatasetBlock(
                    source_tag=source_tag,
                    subtype=subtype_from_tag(source_tag),
                    quality=quality,
                    timestamp_text=timestamp_text,
                    headers=headers,
                    rows=rows,
                )
            )
        source_tag = ""
        quality = ""
        timestamp_text = ""
        headers = []
        rows = []
        in_dataset = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("===="):
            flush()
            continue
        if line.startswith("Tag:"):
            source_tag = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Quality:"):
            quality = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Timestamp:"):
            timestamp_text = line.split(":", 1)[1].strip()
            continue
        if line == "Dataset Contents:":
            in_dataset = True
            continue
        if in_dataset and not headers:
            headers = line.split("\t")
            continue
        if in_dataset:
            values = line.split("\t")
            row = {header: clean_cell(values[index]) if index < len(values) else None for index, header in enumerate(headers)}
            rows.append(row)

    flush()
    return blocks


def parse_equipment(path: Path) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    with path.open(newline="", encoding="utf-8") as equipment_file:
        for line_number, values in enumerate(csv.reader(equipment_file), start=1):
            if not values:
                continue
            if len(values) != len(EQUIPMENT_COLUMNS):
                raise ValueError(
                    f"equipment.txt line {line_number} has {len(values)} columns; "
                    f"expected {len(EQUIPMENT_COLUMNS)}"
                )
            rows.append(dict(zip(EQUIPMENT_COLUMNS, (clean_cell(value) for value in values))))
    return rows


def connect_database(path: Path, preserve: bool) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not preserve:
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tag_subtypes (
            id INTEGER PRIMARY KEY,
            subtype TEXT NOT NULL UNIQUE,
            source_tag TEXT NOT NULL,
            quality TEXT,
            timestamp_text TEXT
        );

        CREATE TABLE IF NOT EXISTS tag_dataset_rows (
            id INTEGER PRIMARY KEY,
            subtype_id INTEGER NOT NULL REFERENCES tag_subtypes(id),
            subtype TEXT NOT NULL,
            tag_name TEXT NOT NULL,
            tag_description TEXT,
            data_type TEXT,
            overview INTEGER,
            detail INTEGER,
            summary INTEGER,
            setpoint INTEGER,
            raw_row_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY,
            subtype_id INTEGER REFERENCES tag_subtypes(id),
            subtype_match_source TEXT,
            name TEXT NOT NULL,
            tag_path TEXT NOT NULL,
            equipment_type TEXT,
            equipment_type_source_id TEXT,
            subtype TEXT,
            subtype_source_id TEXT,
            field_name TEXT,
            route_name TEXT,
            site_name TEXT,
            field_id TEXT,
            route_id TEXT,
            site_id TEXT,
            equipment_id TEXT,
            model_code TEXT,
            device_reference TEXT,
            gathering_system TEXT,
            merrick_id TEXT,
            controller_name TEXT,
            equipment_index TEXT,
            raw_row_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tag_dataset_rows_subtype_id ON tag_dataset_rows(subtype_id);
        CREATE INDEX IF NOT EXISTS idx_equipment_subtype_id ON equipment(subtype_id);
        CREATE INDEX IF NOT EXISTS idx_equipment_name ON equipment(name);
        """
    )


def insert_tag_blocks(connection: sqlite3.Connection, blocks: list[DatasetBlock]) -> dict[str, int]:
    subtype_ids: dict[str, int] = {}
    for block in blocks:
        cursor = connection.execute(
            """
            INSERT INTO tag_subtypes (subtype, source_tag, quality, timestamp_text)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(subtype) DO UPDATE SET
                source_tag = excluded.source_tag,
                quality = excluded.quality,
                timestamp_text = excluded.timestamp_text
            RETURNING id
            """,
            (block.subtype, block.source_tag, block.quality, block.timestamp_text),
        )
        subtype_id = int(cursor.fetchone()["id"])
        subtype_ids[block.subtype.lower()] = subtype_id

        connection.execute("DELETE FROM tag_dataset_rows WHERE subtype_id = ?", (subtype_id,))
        for row in block.rows:
            connection.execute(
                """
                INSERT INTO tag_dataset_rows (
                    subtype_id, subtype, tag_name, tag_description, data_type,
                    overview, detail, summary, setpoint, raw_row_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subtype_id,
                    block.subtype,
                    clean_cell(row.get("TagName")) or "",
                    clean_cell(row.get("TagDescription")),
                    clean_cell(row.get("DataType")),
                    bool_cell(row.get("Overview")),
                    bool_cell(row.get("Detail")),
                    bool_cell(row.get("Summary")),
                    bool_cell(row.get("Setpoint")),
                    json.dumps(row, sort_keys=True),
                ),
            )
    return subtype_ids


def resolve_subtype_id(
    row: dict[str, str | None],
    subtype_ids: dict[str, int],
    map_column: str,
) -> tuple[int | None, str | None]:
    candidates: tuple[str, ...]
    if map_column == "auto":
        candidates = ("subtype", "equipment_type")
    else:
        candidates = (map_column,)

    for candidate in candidates:
        value = (row.get(candidate) or "").lower()
        if value in subtype_ids:
            return subtype_ids[value], candidate

    return None, None


def insert_equipment(
    connection: sqlite3.Connection,
    rows: list[dict[str, str | None]],
    subtype_ids: dict[str, int],
    map_column: str,
) -> tuple[int, int]:
    connection.execute("DELETE FROM equipment")
    unmatched = 0
    for row in rows:
        subtype_id, match_source = resolve_subtype_id(row, subtype_ids, map_column)
        if subtype_id is None:
            unmatched += 1
        connection.execute(
            f"""
            INSERT INTO equipment (
                subtype_id, subtype_match_source, {", ".join(EQUIPMENT_COLUMNS)}, raw_row_json
            )
            VALUES ({", ".join("?" for _ in range(len(EQUIPMENT_COLUMNS) + 3))})
            """,
            (
                subtype_id,
                match_source,
                *(row[column] for column in EQUIPMENT_COLUMNS),
                json.dumps(row, sort_keys=True),
            ),
        )
    return len(rows), unmatched


def main() -> None:
    args = parse_args()
    tag_blocks = parse_tags(args.tags)
    equipment_rows = parse_equipment(args.equipment)

    with connect_database(args.db, args.preserve) as connection:
        create_schema(connection)
        subtype_ids = insert_tag_blocks(connection, tag_blocks)
        equipment_count, unmatched_count = insert_equipment(
            connection, equipment_rows, subtype_ids, args.equipment_map_column
        )
        connection.commit()

    dataset_row_count = sum(len(block.rows) for block in tag_blocks)
    print(f"Wrote {args.db}")
    print(f"tag_subtypes: {len(tag_blocks)}")
    print(f"tag_dataset_rows: {dataset_row_count}")
    print(f"equipment: {equipment_count}")
    if unmatched_count:
        print(f"equipment without subtype match: {unmatched_count}")


if __name__ == "__main__":
    main()
