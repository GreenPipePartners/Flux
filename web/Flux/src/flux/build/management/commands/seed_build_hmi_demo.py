from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from flux.build.services import default_hmi_demo_sqlite_path, seed_hmi_demo_build_sample


class Command(BaseCommand):
    help = "Seed Flux.build with the verified FactoryTalk SQLite recovery sample."

    def add_arguments(self, parser):
        parser.add_argument("--sqlite-path", default=str(default_hmi_demo_sqlite_path()))
        parser.add_argument("--max-display-screens", type=int, default=8)
        parser.add_argument("--output-dir", default="/tmp/opencode/flux-build-hmi-demo")
        parser.add_argument(
            "--keep-existing", action="store_true", help="Do not replace prior HMI demo sample runs"
        )

    def handle(self, *args, **options):
        try:
            build_run = seed_hmi_demo_build_sample(
                sqlite_path=options["sqlite_path"],
                max_display_screens=options["max_display_screens"],
                output_dir=options["output_dir"],
                replace=not options["keep_existing"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Seeded HMI demo Flux.build sample mine_run=%(mine_run)s build_run=%(build_run)s screens=%(screens)s components=%(components)s"
                % {
                    "mine_run": build_run.mine_run_id,
                    "build_run": build_run.id,
                    "screens": build_run.summary.get("screen_count", 0),
                    "components": build_run.summary.get("component_count", 0),
                }
            )
        )
