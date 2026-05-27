from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from flux.schematics.compiler import compile_system
from flux.schematics.fixtures import build_basic_motor_starter_system
from flux.schematics.projections import compile_run_diagnostic_payload


class Command(BaseCommand):
    help = "Build, compile, and report the basic 480 VAC motor starter schematic fixture."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json", help="Emit the diagnostic payload as JSON.")

    def handle(self, *args, **options):
        system = build_basic_motor_starter_system()
        run = compile_system(system)
        payload = compile_run_diagnostic_payload(run)

        if options["as_json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(f"System: {payload['system']['name']} ({payload['system']['slug']})")
        self.stdout.write(f"Compile: {payload['compile_run']['status']}")
        self.stdout.write(
            "Counts: {sources} sources, {circuits} circuits, {components} components".format(**payload["counts"])
        )
        self.stdout.write(f"Findings: {payload['compile_run']['finding_count']}")
        self.stdout.write(f"Terminal bindings: {payload['compile_run']['binding_count']}")
