from __future__ import annotations

import argparse

from flux_sim.provider_import import import_provider_export
from flux_sim.tag_data import load_tag_data_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an Ignition tag provider export into SQLite.")
    parser.add_argument("source", help="Path to Ignition tag provider JSON export")
    parser.add_argument("--database", "-d", required=True, help="SQLite database path to create/update")
    parser.add_argument("--provider", default="ACM02", help="Provider name to materialize")
    parser.add_argument("--devices", help="Optional device inventory text file to correlate with the provider export")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--skip-raw-config", action="store_true")
    args = parser.parse_args()

    result = import_provider_export(
        args.source,
        args.database,
        provider_name=args.provider,
        batch_size=args.batch_size,
        keep_raw_config=not args.skip_raw_config,
    )
    print(
        "Imported {total} nodes for provider {provider} "
        "({folders} folders, {atomic} atomic tags, {udts} UDT instances, {types} UDT types)".format(
            total=result.total_nodes,
            provider=result.provider_name,
            folders=result.counts.get("Folder", 0),
            atomic=result.counts.get("AtomicTag", 0),
            udts=result.counts.get("UdtInstance", 0),
            types=result.counts.get("UdtType", 0),
        )
    )
    if args.devices:
        catalog = load_tag_data_catalog(args.provider, devices_path=args.devices, tags_path=args.source)
        print(
            "Catalog {provider}: {devices} devices, {refs} atomic tag references, "
            "{unknown} unknown referenced devices, {unused} unreferenced inventory devices".format(
                provider=catalog.provider_name,
                devices=len(catalog.devices),
                refs=len(catalog.tag_references),
                unknown=len(catalog.unknown_device_names),
                unused=len(catalog.unreferenced_device_names),
            )
        )
        for profile in catalog.device_profiles()[:20]:
            print(
                "  {name}: driver={driver} strategy={strategy} tags={tags}".format(
                    name=profile.device.name,
                    driver=profile.device.driver,
                    strategy=profile.device.strategy_key,
                    tags=profile.tag_count,
                )
            )


if __name__ == "__main__":
    main()
