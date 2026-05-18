import os

from django.core.management.base import BaseCommand, CommandError

from serve.worker import run_worker_heartbeat


class Command(BaseCommand):
    help = "Run the dedicated Flux Trace cache worker."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-trace-worker")
        parser.add_argument("--interval", type=float, default=60.0)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--profile-key", default="")
        parser.add_argument("--nav-well-live", action="store_true")
        parser.add_argument("--nav-well-limit", type=int, default=None)
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))

    def handle(self, *args, **options):
        try:
            import fluxy
        except ImportError as exc:
            raise CommandError("Install fluxy before running the trace worker") from exc

        fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])

        if options["nav_well_live"]:
            from trace.providers.nav_wells import seeded_well_profiles, sync_nav_well_trace_cache, update_nav_well_live_values
            from trace.questdb_data_plane import export_trace_cache_to_questdb

            def job():
                updated = update_nav_well_live_values(fx, limit=options["nav_well_limit"])
                result = sync_nav_well_trace_cache(fx, limit=options["nav_well_limit"], force=True)
                profiles = seeded_well_profiles()
                if options["nav_well_limit"]:
                    profiles = profiles[: options["nav_well_limit"]]
                questdb_points = export_trace_cache_to_questdb(profile_keys=[profile.key for profile in profiles])
                return "nav_well_live updated=%s profiles=%s signals=%s points=%s questdb_points=%s" % (
                    updated,
                    result.profile_count,
                    result.signal_count,
                    result.point_count,
                    questdb_points,
                )

            job_name = "trace_nav_well_live"
        else:
            from trace.cache import sync_trace_cache

            profile_key = options["profile_key"] or None

            def job():
                result = sync_trace_cache(fx, profile_key=profile_key)
                return "cache profiles=%s signals=%s points=%s" % (
                    result.profile_count,
                    result.signal_count,
                    result.point_count,
                )

            job_name = "trace_cache"

        run_worker_heartbeat(
            service_name=options["service_name"],
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
            job_name=job_name,
            job=job,
        )
