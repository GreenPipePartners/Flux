from __future__ import annotations

import argparse
import json
from pathlib import Path

from flux_mine.plc.l5k import parse_l5k_file
from flux_mine.plc.l5x import parse_l5x_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flux.mine source recovery utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    l5x = subparsers.add_parser("parse-l5x", help="Parse an L5X file and print a summary")
    l5x.add_argument("path")
    l5k = subparsers.add_parser("parse-l5k", help="Parse an L5K file and print a summary")
    l5k.add_argument("path")

    args = parser.parse_args(argv)
    if args.command == "parse-l5x":
        project = parse_l5x_file(Path(args.path))
        print(json.dumps(project.summary(), indent=2, sort_keys=True))
        return 0
    if args.command == "parse-l5k":
        project = parse_l5k_file(Path(args.path))
        print(json.dumps(project.summary(), indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
