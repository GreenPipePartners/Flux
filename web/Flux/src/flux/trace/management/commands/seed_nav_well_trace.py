import os

from django.core.management.base import BaseCommand, CommandError

from flux.chart.providers.nav_wells import clear_nav_well_plane_samples, configure_nav_well_ignition_tags, inject_nav_well_history, seed_nav_well_trace_config, sync_nav_well_plane_samples, update_nav_well_live_values


class Command(BaseCommand):
    help = "Seed process-agnostic trace profiles/signals from navigation wells."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--window-minutes", type=int, default=1440)
        parser.add_argument("--configure-ignition", action="store_true")
        parser.add_argument("--inject-history", action="store_true")
        parser.add_argument("--sync-cache", action="store_true")
        parser.add_argument("--update-live", action="store_true")
        parser.add_argument("--local-bootstrap-cache", action="store_true")
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))

    def handle(self, *args, **options):
        use_ignition_path = options["configure_ignition"] or options["inject_history"] or options["sync_cache"] or options["update_live"]
        result = seed_nav_well_trace_config(
            limit=options["limit"],
            seed_cache=options["local_bootstrap_cache"] or not use_ignition_path,
            window_minutes=options["window_minutes"],
        )
        self.stdout.write("Seeded wells=%s profiles=%s tags=%s signals=%s" % (result["wells"], result["profiles"], result["tags"], result["signals"]))
        if not use_ignition_path:
            return
        try:
            import fluxy
        except ImportError as exc:
            raise CommandError("Install fluxy before configuring Ignition trace tags") from exc
        fx = fluxy.Fluxy(base_url=options["base_url"], token=options["token"])
        if options["configure_ignition"]:
            self.stdout.write("Configured %s Ignition tags" % configure_nav_well_ignition_tags(fx, limit=options["limit"]))
        if options["inject_history"]:
            self.stdout.write("Cleared %s local Plane sample points before Ignition historian sync" % clear_nav_well_plane_samples(limit=options["limit"]))
            self.stdout.write("Injected %s historian points" % inject_nav_well_history(fx, limit=options["limit"], window_minutes=options["window_minutes"]))
        if options["update_live"]:
            self.stdout.write("Updated %s live Ignition tag values" % update_nav_well_live_values(fx, limit=options["limit"]))
        if options["sync_cache"] or options["inject_history"] or options["update_live"]:
            result = sync_nav_well_plane_samples(fx, limit=options["limit"])
            self.stdout.write("Synced Plane samples profiles=%s signals=%s points=%s" % (result.profile_count, result.signal_count, result.point_count))
