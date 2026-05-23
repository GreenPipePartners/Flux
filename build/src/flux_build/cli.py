from __future__ import annotations

import argparse
import json
from pathlib import Path

from flux_build.targets.ignition_tags import build_ignition_provider
from flux_mine.plc.parsers import parse_plc_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flux.build target generation utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    tags = subparsers.add_parser("ignition-tags", help="Generate Ignition tag provider JSON from L5X/L5K")
    tags.add_argument("path")
    tags.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    if args.command == "ignition-tags":
        project = parse_plc_file(Path(args.path))
        result = build_ignition_provider(project)
        Path(args.output).write_text(json.dumps(result.provider, indent=2), encoding="utf-8")
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
