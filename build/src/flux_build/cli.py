from __future__ import annotations

import argparse
import json
from pathlib import Path

from flux_build.hmi.adapters import hmi_map_project_from_factorytalk
from flux_build.hmi.symbolic import build_symbolic_hmi_map
from flux_build.targets.ignition_tags import build_ignition_provider
from flux_mine.hmi.factorytalk import FactoryTalkProject
from flux_mine.imports import parse_import_path
from flux_mine.plc.parsers import parse_plc_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flux.build target generation utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tags = subparsers.add_parser("ignition-tags", help="Generate Ignition tag provider JSON from L5X/L5K")
    tags.add_argument("path")
    tags.add_argument("--output", required=True)
    hmi_map = subparsers.add_parser("hmi-map", help="Generate vendor-neutral symbolic HMI map JSON/SVG from an HMI source")
    hmi_map.add_argument("path")
    hmi_map.add_argument("--output-dir", required=True)

    args = parser.parse_args(argv)
    if args.command == "ignition-tags":
        project = parse_plc_file(Path(args.path))
        result = build_ignition_provider(project)
        Path(args.output).write_text(json.dumps(result.provider, indent=2), encoding="utf-8")
        return 0
    if args.command == "hmi-map":
        imported = parse_import_path(Path(args.path), source_type="factorytalk")
        if not isinstance(imported.project, FactoryTalkProject):
            raise ValueError("HMI map builds require an HMI source")
        result = build_symbolic_hmi_map(hmi_map_project_from_factorytalk(imported.project))
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "hmi_map.json").write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
        screens_dir = output_dir / "screens"
        screens_dir.mkdir(exist_ok=True)
        for screen_key, svg in result.svg_by_screen.items():
            (screens_dir / f"{safe_filename(screen_key)}.svg").write_text(svg, encoding="utf-8")
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


def safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return cleaned.strip("_") or "screen"


if __name__ == "__main__":
    raise SystemExit(main())
