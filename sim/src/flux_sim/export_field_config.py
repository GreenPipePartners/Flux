from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from flux_sim.field_config import build_field_agent_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Flux Sim provider data as FieldAgent config JSON.")
    parser.add_argument("--database", "-d", required=True, help="SQLite database created by flux-sim-import-provider")
    parser.add_argument("--provider", default="ACM02")
    parser.add_argument("--output", "-o", help="Optional output path. Writes stdout when omitted.")
    parser.add_argument("--endpoint-url", default="opc.tcp://localhost:4840/flux/sim")
    parser.add_argument("--namespace-uri", default="urn:flux:sim")
    parser.add_argument("--include-unresolved", action="store_true")
    args = parser.parse_args()

    try:
        config = build_field_agent_config(
            args.database,
            provider_name=args.provider,
            endpoint_url=args.endpoint_url,
            namespace_uri=args.namespace_uri,
            include_unresolved=args.include_unresolved,
        )
    except ImportError as exc:
        raise SystemExit(
            "fluxy.ignition_expression is required to flatten UDT OPC requests. "
            "Install fluxy or set PYTHONPATH to fluxy/src."
        ) from exc

    text = json.dumps(config, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
