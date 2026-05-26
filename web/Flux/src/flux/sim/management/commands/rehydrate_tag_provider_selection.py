from __future__ import annotations

import json
import os

from django.core.management.base import BaseCommand

import fluxy
from flux.sim.rehydrate import (
    apply_rehydration_plan,
    build_rehydration_plan,
    materialize_rehydration_backing,
    rehydration_configure_operations,
)


class Command(BaseCommand):
    help = "Rehydrate selected imported tag branches into an existing Ignition provider with original paths preserved."

    def add_arguments(self, parser):
        parser.add_argument("source_provider", help="Imported Flux tag provider, for example Tag_02.")
        parser.add_argument(
            "--target-provider",
            default=None,
            help="Existing Ignition tag provider to configure. Flux will not create this provider.",
        )
        parser.add_argument(
            "--selected-path",
            action="append",
            dest="selected_paths",
            help="Optional selected source path. Repeat to bypass stored Flux.sim selections.",
        )
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument("--collision-policy", default="o", choices=["a", "m", "o", "i"])
        parser.add_argument("--no-backing", action="store_true", help="Do not materialize FieldAgent backing nodes.")
        parser.add_argument("--dry-run", action="store_true", help="Print the generated system.tag.configure payload only.")

    def handle(self, *args, **options):
        plan = build_rehydration_plan(
            options["source_provider"],
            target_provider=options["target_provider"],
            selected_paths=options["selected_paths"],
        )
        payload = {
            "base_path": plan.tag_base_path,
            "tags": plan.tag_configs,
            "operations": [
                {"base_path": operation.base_path, "tags": operation.tag_configs}
                for operation in rehydration_configure_operations(plan)
            ],
            "summary": {
                "source_provider": plan.source_provider,
                "target_provider": plan.target_provider,
                "selected_node_count": plan.selected_node_count,
                "udt_dependency_count": plan.udt_dependency_count,
                "tag_count": plan.tag_count,
            },
        }
        if options["dry_run"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        backing = None
        if not options["no_backing"]:
            backing = materialize_rehydration_backing(
                options["source_provider"],
                selected_paths=options["selected_paths"],
            )
        client = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])
        apply_rehydration_plan(client, plan, collision_policy=options["collision_policy"])
        if backing is not None:
            self.stdout.write(
                "Materialized %(tags)s FieldAgent backing tag(s) across %(devices)s device(s) and %(endpoints)s endpoint(s); skipped %(skipped)s"
                % {
                    "tags": backing.tag_count,
                    "devices": backing.device_count,
                    "endpoints": backing.endpoint_count,
                    "skipped": backing.skipped_count,
                }
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Rehydrated %(tag_count)s tag config node(s) from %(source)s into %(target)s"
                % {
                    "tag_count": plan.tag_count,
                    "source": plan.source_provider,
                    "target": plan.tag_base_path,
                }
            )
        )
