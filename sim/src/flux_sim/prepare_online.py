from __future__ import annotations

import argparse
import json
from pathlib import Path

from flux_sim.field_config import build_field_agent_config
from flux_sim.provider_import import import_provider_export


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a Flux Sim provider database and FieldAgent config for online testing."
    )
    parser.add_argument("source", help="Path to Ignition tag provider JSON export")
    parser.add_argument("--provider", default="ACM02", help="Provider name to materialize")
    parser.add_argument("--database", "-d", default="flux-sim.db", help="SQLite database path")
    parser.add_argument(
        "--field-config",
        "-o",
        default="field-config.sim.json",
        help="FieldAgent config output path",
    )
    parser.add_argument("--endpoint-url", default="opc.tcp://localhost:4840/flux/sim")
    parser.add_argument("--namespace-uri", default="urn:flux:sim")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--include-unresolved", action="store_true")
    args = parser.parse_args()

    database_path = Path(args.database)
    field_config_path = Path(args.field_config)

    result = import_provider_export(
        args.source,
        database_path,
        provider_name=args.provider,
        batch_size=args.batch_size,
        keep_raw_config=True,
    )
    config = build_field_agent_config(
        database_path,
        provider_name=args.provider,
        endpoint_url=args.endpoint_url,
        namespace_uri=args.namespace_uri,
        include_unresolved=args.include_unresolved,
    )
    field_config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    endpoint = config["endpoints"][0]
    tag_count = sum(len(device["tags"]) for device in endpoint["devices"])
    print(
        "Prepared provider {provider}: {nodes} imported nodes, {devices} devices, {tags} FieldAgent tags".format(
            provider=args.provider,
            nodes=result.total_nodes,
            devices=len(endpoint["devices"]),
            tags=tag_count,
        )
    )
    print(f"Database: {database_path}")
    print(f"FieldAgent config: {field_config_path}")
    print(f"Endpoint URL: {args.endpoint_url}")


if __name__ == "__main__":
    main()
