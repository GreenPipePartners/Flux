from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.build.services import build_ignition_tags_from_mine_run


class Command(BaseCommand):
    help = "Build Ignition tag provider JSON from a persisted Flux.mine PLC run."

    def add_arguments(self, parser):
        parser.add_argument("mine_run_id", type=int, help="Flux.mine run id to build from")
        parser.add_argument("--output", required=True, help="Output path for generated provider JSON")

    def handle(self, *args, **options):
        try:
            run = build_ignition_tags_from_mine_run(options["mine_run_id"], options["output"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Built run %(id)s artifact=%(path)s sha256=%(sha)s bytes=%(bytes)s"
                % {
                    "id": run.id,
                    "path": run.output_path,
                    "sha": run.output_sha256,
                    "bytes": run.output_bytes,
                }
            )
        )
