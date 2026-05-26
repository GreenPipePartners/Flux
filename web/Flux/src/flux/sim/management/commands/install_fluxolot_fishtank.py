import os

from django.core.management.base import BaseCommand, CommandError

from flux.plane import seed_plane_samples_from_runtime_history
from flux.serve.field_supervisor import DEFAULT_FIELD_AGENT_HOST, server_endpoint_url
from flux.sim.fluxolot_fishtank import (
    FLUXOLOT_TAG_FOLDER,
    configure_fluxolot_fishtank_ignition,
    ensure_fluxolot_fishtank,
    ensure_fluxolot_live_scope,
    ensure_fluxolot_trace_profiles,
    write_fluxolot_live_csv,
    write_fluxolot_trace_csv,
)


class Command(BaseCommand):
    help = "Install or update the persistent Fluxolot Fishtank verification fixture."

    def add_arguments(self, parser):
        parser.add_argument("--history-days", type=int, default=30)
        parser.add_argument("--history-years", type=int, default=0, help="Seed years of Fluxolot history. Overrides --history-days when set.")
        parser.add_argument(
            "--long-history",
            action="store_true",
            help="Seed the recommended three-year Flux.plane proof dataset at 15-minute resolution unless overridden.",
        )
        parser.add_argument("--history-interval-minutes", type=int, default=60)
        parser.add_argument("--history-batch-size", type=int, default=5000)
        parser.add_argument(
            "--plane-samples-all",
            action="store_true",
            help="Seed Plane sample rows for all generated Fluxolot history instead of the recent sample limit.",
        )
        parser.add_argument("--plane-sample-limit", type=int, default=48)
        parser.add_argument("--plane-sample-batch-size", type=int, default=5000)
        parser.add_argument(
            "--export-questdb",
            action="store_true",
            help="Export Fluxolot Plane sample rows into QuestDB plane_samples for Flux.plane proof.",
        )
        parser.add_argument(
            "--replace-questdb",
            action="store_true",
            help="Replace the QuestDB plane_samples table before exporting Fluxolot Plane sample rows.",
        )
        parser.add_argument("--live-csv", help="Write a Live scope CSV fixture for Fluxolot Fishtank RuntimeTags.")
        parser.add_argument("--trace-csv", help="Write a trace sample CSV fixture from Fluxolot Fishtank RuntimeTags.")
        parser.add_argument(
            "--configure-ignition",
            action="store_true",
            help="Configure Fluxolot Fishtank OPC UA connections and OPC tags in Ignition using Fluxy.",
        )
        parser.add_argument("--base-url", default=os.getenv("FLUXY_BASE_URL", "http://localhost:8088/system/webdev/flux"))
        parser.add_argument("--token", default=os.getenv("FLUXY_TOKEN"))
        parser.add_argument(
            "--project-location",
            default=os.getenv("FLUXY_PROJECT_LOCATION"),
            help="Optional Ignition project filesystem path for Fluxy project helpers.",
        )
        parser.add_argument("--tag-provider", default="default")
        parser.add_argument("--tag-folder", default=FLUXOLOT_TAG_FOLDER)
        parser.add_argument(
            "--field-agent-base-port",
            type=int,
            default=4850,
            help="Base port used by flux_field_supervisor when computing served FieldAgent endpoint URLs.",
        )
        parser.add_argument(
            "--field-agent-host",
            default=DEFAULT_FIELD_AGENT_HOST,
            help="Connectable host advertised in supervised Fluxolot FieldAgent endpoint URLs.",
        )
        parser.add_argument(
            "--collision-policy",
            default="o",
            choices=["a", "m", "o", "i"],
            help="Ignition system.tag.configure collision policy.",
        )
        parser.add_argument(
            "--no-cleanup",
            action="store_true",
            help="Do not delete the target tag folder or remove the generated OPC UA connections first.",
        )

    def handle(self, *args, **options):
        history_days = options["history_days"]
        history_interval_minutes = options["history_interval_minutes"]
        if options["history_years"]:
            history_days = options["history_years"] * 365
        elif options["long_history"]:
            history_days = 365 * 3
        if options["long_history"] and history_interval_minutes == 60:
            history_interval_minutes = 15
        result = ensure_fluxolot_fishtank(
            history_days=history_days,
            history_interval_minutes=history_interval_minutes,
            history_batch_size=options["history_batch_size"],
        )
        live_scope = ensure_fluxolot_live_scope(result.runtime_tags)
        trace_profiles = ensure_fluxolot_trace_profiles(
            result.runtime_tags,
            cache_window_minutes=history_days * 1440 if options["long_history"] or options["history_years"] else 10080,
        )
        sample_limit = None if options["plane_samples_all"] or options["long_history"] else options["plane_sample_limit"]
        plane_sample_points = sum(
            seed_plane_samples_from_runtime_history(
                profile,
                sample_limit=sample_limit,
                batch_size=options["plane_sample_batch_size"],
            )
            for profile in trace_profiles
        )
        questdb_points = 0
        if options["export_questdb"]:
            from flux.chart.questdb_data_plane import export_plane_samples_to_questdb

            questdb_points = export_plane_samples_to_questdb(
                profile_keys=[profile.key for profile in trace_profiles],
                replace=options["replace_questdb"],
                batch_size=options["plane_sample_batch_size"],
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Installed Fluxolot Fishtank: endpoints=%s devices=%s tags=%s runtime_tags=%s samples=%s live=%s trace=%s plane_sample_points=%s questdb_points=%s"
                % (
                    len(result.endpoints),
                    len(result.devices),
                    len(result.field_tags),
                    len(result.runtime_tags),
                    result.sample_count,
                    live_scope.slug,
                    ",".join(profile.key for profile in trace_profiles),
                    plane_sample_points,
                    questdb_points,
                )
            )
        )
        if options["live_csv"]:
            rows = write_fluxolot_live_csv(options["live_csv"])
            self.stdout.write(self.style.SUCCESS("Wrote Fluxolot live CSV rows=%s path=%s" % (rows, options["live_csv"])))
        if options["trace_csv"]:
            rows = write_fluxolot_trace_csv(options["trace_csv"])
            self.stdout.write(self.style.SUCCESS("Wrote Fluxolot trace CSV rows=%s path=%s" % (rows, options["trace_csv"])))
        if options["configure_ignition"]:
            try:
                import fluxy
            except ImportError as exc:
                raise CommandError("Install fluxy before configuring Fluxolot Fishtank in Ignition") from exc

            client = fluxy.Fluxy(
                base_url=options["base_url"],
                token=options["token"],
                project_location=options["project_location"],
            )
            endpoint_urls = {
                endpoint.name: server_endpoint_url(
                    endpoint,
                    base_port=options["field_agent_base_port"],
                    host=options["field_agent_host"],
                )
                for endpoint in result.endpoints
            }
            ignition = configure_fluxolot_fishtank_ignition(
                client,
                tag_provider=options["tag_provider"],
                tag_folder=options["tag_folder"],
                endpoint_urls=endpoint_urls,
                cleanup_existing=not options["no_cleanup"],
                collision_policy=options["collision_policy"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Configured Fluxolot Fishtank Ignition connection(s)=%s tags=%s under %s%s"
                    % (
                        len(ignition.connection_names),
                        ignition.tag_count,
                        ignition.tag_base_path,
                        ignition.tag_folder,
                    )
                )
            )
