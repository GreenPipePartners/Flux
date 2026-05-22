import os

from django.core.management.base import BaseCommand, CommandError

from flux.base.runtime import RuntimeTag
from flux.opt.services import runtime_tags_for_prefix, sample_due_runtime_tags, sample_runtime_tags
from serve.worker import run_worker_heartbeat


class Command(BaseCommand):
    help = "Run the dedicated Flux runtime tag sampling worker."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-sampling-worker")
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--profile", choices=["fluxolot-fishtank"], help="Sample a named runtime tag profile instead of general due tags.")
        parser.add_argument("--provider", default="default")
        parser.add_argument("--path-prefix", default="")
        parser.add_argument("--runtime-category", default="")
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))

    def handle(self, *args, **options):
        try:
            import fluxy
        except ImportError as exc:
            raise CommandError("Install fluxy before running the sampling worker") from exc

        fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])
        profile = options["profile"]
        service_name = options["service_name"]
        path_prefix = options["path_prefix"]
        runtime_category = options["runtime_category"]
        if profile == "fluxolot-fishtank":
            if service_name == "flux-sampling-worker":
                service_name = "fluxolot-live-sampler"
            if not path_prefix:
                path_prefix = "FluxolotFishtank/"
            if not runtime_category:
                runtime_category = RuntimeTag.Category.SIMULATION

        def job():
            if profile:
                tags = runtime_tags_for_prefix(
                    provider=options["provider"],
                    path_prefix=path_prefix,
                    category=runtime_category,
                    limit=options["batch_size"],
                )
                if not tags:
                    raise CommandError("No runtime tags matched profile=%s provider=%s path_prefix=%s" % (profile, options["provider"], path_prefix))
                sampled = sample_runtime_tags(tags, fx=fx)
                return "profile=%s sampled=%s tags=%s" % (profile, sampled, len(tags))
            sampled = sample_due_runtime_tags(fx=fx, limit=options["batch_size"])
            return "sampled=%s" % sampled

        run_worker_heartbeat(
            service_name=service_name,
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
            job_name="sample_profile:%s" % profile if profile else "sample_due_runtime_tags",
            job=job,
        )
