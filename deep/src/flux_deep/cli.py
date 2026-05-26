from __future__ import annotations

import argparse
import json
from pathlib import Path

from flux_deep.hello_world import write_hello_world_workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flux.Deep OpenPLC emulation utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser(
        "init-hello-world",
        help="Create the starter Logix/OpenPLC hello_world workspace",
    )
    init.add_argument("--output", default="hello_world", help="Output workspace directory")
    init.add_argument("--force", action="store_true", help="Overwrite generated files")

    inspect = subparsers.add_parser("inspect", help="Print a Flux.Deep workspace manifest")
    inspect.add_argument("path", help="Workspace directory containing manifest.json")

    args = parser.parse_args(argv)
    if args.command == "init-hello-world":
        written = write_hello_world_workspace(Path(args.output), overwrite=args.force)
        for path in written:
            print(path)
        return 0
    if args.command == "inspect":
        manifest_path = Path(args.path) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
