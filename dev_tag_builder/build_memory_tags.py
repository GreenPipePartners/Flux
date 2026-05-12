#!/usr/bin/env python3
"""Carl's offline tag import builder for Flux/Ignition trials.

Reads instance_exports.sqlite3, expands equipment rows by tag dataset rows, and
emits:
- providers.txt: tag providers that must exist in Ignition.
- tag_paths.txt: unique fully-qualified tag paths.
- import_<provider>.json: Ignition provider-root tag import JSON.

The source SQL requested for Ignition-style tag path expansion is logically:

    select concat('"', tag_path, '/', tag_name, '",')
    from tag_dataset_rows
    join equipment on tag_dataset_rows.subtype_id = equipment.subtype_id

SQLite does not have concat() by default, so this tool uses the equivalent
`equipment.tag_path || '/' || tag_dataset_rows.tag_name` expression.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


DEFAULT_DB = Path("../instance_exports.sqlite3")
DEFAULT_OUTPUT_DIR = Path("out")

TAG_QUERY = """
select equipment.tag_path || '/' || tag_dataset_rows.tag_name as tag_path
from tag_dataset_rows
join equipment on tag_dataset_rows.subtype_id = equipment.subtype_id
order by equipment.tag_path, tag_dataset_rows.tag_name
"""

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--default-value", default="1")
    parser.add_argument("--data-type", default="Float4", choices=("Float4", "Float8"))
    parser.add_argument(
        "--include-types-folder",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include the _types_ folder seen in Ignition provider exports.",
    )
    return parser.parse_args()


def load_tag_paths(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        rows = [row[0] for row in connection.execute(TAG_QUERY)]

    seen = set()
    unique_paths = []
    for tag_path in rows:
        if tag_path in seen:
            continue
        seen.add(tag_path)
        unique_paths.append(tag_path)
    return unique_paths


def split_provider(tag_path: str) -> tuple[str, str]:
    if not tag_path.startswith("[") or "]" not in tag_path:
        raise ValueError("Tag path must start with [provider]: %s" % tag_path)
    provider, relative_path = tag_path[1:].split("]", 1)
    return provider, relative_path.strip("/")


def folder_config(name: str) -> dict[str, str]:
    return {"name": name, "tagType": "Folder"}


def memory_float_config(name: str, data_type: str, default_value: int | float) -> dict[str, object]:
    return {
        "dataType": data_type,
        "defaultValue": default_value,
        "name": name,
        "tagType": "AtomicTag",
        "value": default_value,
        "valueSource": "memory",
    }


def parse_default_value(value: str) -> int | float:
    numeric = float(value)
    if numeric.is_integer():
        return int(numeric)
    return numeric


def child_lookup(node: dict[str, object]) -> dict[str, dict[str, object]]:
    lookup = node.setdefault("_child_lookup", {})
    return lookup  # type: ignore[return-value]


def children(node: dict[str, object]) -> list[dict[str, object]]:
    tags = node.setdefault("tags", [])
    return tags  # type: ignore[return-value]


def add_child(parent: dict[str, object], child: dict[str, object]) -> dict[str, object]:
    lookup = child_lookup(parent)
    name = str(child["name"])
    if name in lookup:
        return lookup[name]
    lookup[name] = child
    children(parent).append(child)
    return child


def add_path(root: dict[str, object], parts: list[str], data_type: str, default_value: int | float) -> None:
    node = root
    for folder_name in parts[:-1]:
        node = add_child(node, folder_config(folder_name))
    add_child(node, memory_float_config(parts[-1], data_type, default_value))


def strip_internal_lookups(node: dict[str, object]) -> None:
    node.pop("_child_lookup", None)
    for child in node.get("tags", []):
        strip_internal_lookups(child)  # type: ignore[arg-type]


def build_import_roots_by_provider(
    tag_paths: list[str], data_type: str, default_value: int | float, include_types_folder: bool
) -> dict[str, dict[str, object]]:
    providers: dict[str, dict[str, object]] = {}

    for tag_path in tag_paths:
        provider, relative_path = split_provider(tag_path)
        parts = [part for part in relative_path.split("/") if part]
        if not parts:
            continue

        root = providers.setdefault(provider, {"name": "", "tagType": "Provider", "tags": []})
        add_path(root, parts, data_type, default_value)

    if include_types_folder:
        for root in providers.values():
            add_child(root, folder_config("_types_"))

    for root in providers.values():
        strip_internal_lookups(root)

    return providers


def write_provider_summary(output_dir: Path, tag_paths: list[str]) -> list[str]:
    counts = Counter(split_provider(path)[0] for path in tag_paths)
    providers = sorted(counts)
    lines = ["# Providers required in Ignition", ""]
    for provider in providers:
        lines.append("%s\t%s" % (provider, counts[provider]))
    output_dir.joinpath("providers.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return providers


def write_tag_paths(output_dir: Path, tag_paths: list[str]) -> None:
    output_dir.joinpath("tag_paths.txt").write_text("\n".join(tag_paths) + "\n", encoding="utf-8")


def safe_provider_filename(provider: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", provider)


def write_import_json_files(
    output_dir: Path,
    import_roots_by_provider: dict[str, dict[str, object]],
) -> None:
    old_script = output_dir / "configure_memory_float_tags.py"
    if old_script.exists():
        old_script.unlink()

    manifest = []
    for provider, root in sorted(import_roots_by_provider.items()):
        filename = "import_%s.json" % safe_provider_filename(provider)
        path = output_dir / filename
        path.write_text(json.dumps(root, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        manifest.append({"provider": provider, "file": filename})

    output_dir.joinpath("manifest.json").write_text(
        json.dumps({"imports": manifest}, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tag_paths = load_tag_paths(args.db)
    default_value = parse_default_value(args.default_value)
    providers = write_provider_summary(output_dir, tag_paths)
    write_tag_paths(output_dir, tag_paths)
    import_roots_by_provider = build_import_roots_by_provider(
        tag_paths, args.data_type, default_value, args.include_types_folder
    )
    write_import_json_files(output_dir, import_roots_by_provider)

    print("tag_paths: %d" % len(tag_paths))
    print("providers: %s" % ", ".join(providers))
    print("output_dir: %s" % output_dir)


if __name__ == "__main__":
    main()
