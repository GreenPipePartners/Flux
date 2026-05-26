from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.build.services import build_hmi_symbolic_map_from_mine_run


class Command(BaseCommand):
    help = "Build vendor-neutral symbolic HMI map artifacts from a persisted Flux.mine HMI run."

    def add_arguments(self, parser):
        parser.add_argument("mine_run_id", type=int, help="Flux.mine HMI run id to build from")
        parser.add_argument("--output-dir", required=True, help="Output directory for symbolic map JSON and SVG artifacts")

    def handle(self, *args, **options):
        try:
            run = build_hmi_symbolic_map_from_mine_run(options["mine_run_id"], options["output_dir"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Built HMI map run %(id)s artifacts=%(artifacts)s components=%(components)s"
                % {
                    "id": run.id,
                    "artifacts": run.summary.get("artifact_count", 0),
                    "components": run.summary.get("component_count", 0),
                }
            )
        )
