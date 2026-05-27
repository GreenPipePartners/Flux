from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.build.services import build_logix_l5k_from_mine_run


class Command(BaseCommand):
    help = "Build a generated Logix L5K artifact from a Flux.mine PLC run."

    def add_arguments(self, parser):
        parser.add_argument("mine_run_id", type=int, help="MineRun id containing PLC source facts")
        parser.add_argument("--output", required=True, help="Output path for generated .L5K")

    def handle(self, *args, **options):
        try:
            run = build_logix_l5k_from_mine_run(options["mine_run_id"], options["output"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Built Logix L5K run %(id)s status=%(status)s output=%(output)s"
                % {"id": run.id, "status": run.status, "output": run.output_path}
            )
        )
