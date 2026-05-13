import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError

from flux.field.demo import ensure_demo_field_config
from flux.opt.demo import configure_demo_ignition_tags, ensure_demo_runtime_config, read_demo_runtime_values
from runtime.scheduler import advance_balancer_code, scheduler_config


class Command(BaseCommand):
    help = "Configure and read the Flux Field well/meter/tank demo into Flux runtime tables."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument("--project-location", default=os.getenv("FLUXY_PROJECT_LOCATION", "../ignition_flux_project"))
        parser.add_argument("--opc-server", default=os.getenv("FLUX_FIELD_OPC_SERVER", "Flux Field"))
        parser.add_argument("--configure-ignition", action="store_true")
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=None)
        parser.add_argument("--cold-balanced", action="store_true")
        parser.add_argument("--retries", type=int, default=3)

    def handle(self, *args, **options):
        try:
            import fluxy
        except ImportError as exc:
            raise CommandError("Install fluxy before running the field demo") from exc

        ensure_demo_field_config()
        runtime_tags = ensure_demo_runtime_config()
        self.stdout.write("Prepared %s runtime tags for Flux Field demo" % len(runtime_tags))

        fx = fluxy.Fluxy(
            base_url=options["base_url"],
            token=options["token"],
            project_location=options["project_location"],
        )
        if options["configure_ignition"]:
            results = configure_demo_ignition_tags(fx, opc_server=options["opc_server"])
            self.stdout.write("Configured %s Ignition demo tags" % len(results))

        while True:
            config = scheduler_config()
            runtime_tags = ensure_demo_runtime_config()
            if options["cold_balanced"]:
                runtime_tags = [tag for tag in runtime_tags if tag.balancer_code == config.current_balancer_code]
            read_count = self.read_with_retries(fx, retries=options["retries"], runtime_tags=runtime_tags)
            if read_count is not None:
                self.stdout.write("Read %s Flux Field demo tags" % read_count)
            if options["cold_balanced"]:
                next_code = advance_balancer_code(config=config)
                self.stdout.write("Advanced Flux Field demo balancer code to %s" % next_code)
            if options["once"]:
                return
            time.sleep(options["interval"] or config.warm_interval_seconds)

    def read_with_retries(self, fx, *, retries: int, runtime_tags):
        for attempt in range(retries + 1):
            try:
                return read_demo_runtime_values(fx, runtime_tags=runtime_tags)
            except OperationalError as exc:
                if "database is locked" not in str(exc).lower() or attempt >= retries:
                    raise
                delay = min(2**attempt, 5)
                self.stderr.write(
                    "Database locked during demo read; retrying in %ss (%s/%s)"
                    % (delay, attempt + 1, retries)
                )
                time.sleep(delay)
            except Exception as exc:
                if exc.__class__.__name__ != "FluxyError":
                    raise
                self.stderr.write("Flux Field demo read failed; will retry next interval: %s" % exc)
                return None
        return None
