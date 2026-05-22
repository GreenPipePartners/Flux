import os

from django.conf import settings
from django.core.management.base import BaseCommand

from flux.serve.monitor import MonitorOptions, refresh_service_snapshots
from serve.worker import run_worker_heartbeat


class Command(BaseCommand):
    help = "Run the dedicated Flux.serve health control-plane monitor."

    def add_arguments(self, parser):
        parser.add_argument("--service-name", default="flux-serve-monitor")
        parser.add_argument("--interval", type=float, default=5.0)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--web-url", default=os.getenv("FLUX_WEB_URL", "http://localhost:8000/"))
        parser.add_argument("--docs-url", default=os.getenv("FLUX_DOCS_URL", "http://localhost:8001/"))
        parser.add_argument("--questdb-host", default=os.getenv("FLUX_QUESTDB_HOST", "localhost"))
        parser.add_argument("--questdb-http-port", type=int, default=int(os.getenv("FLUX_QUESTDB_HTTP_PORT", "9000")))
        parser.add_argument("--questdb-pg-port", type=int, default=int(os.getenv("FLUX_QUESTDB_PG_PORT", "8812")))
        parser.add_argument("--timeout", type=float, default=1.0)
        parser.add_argument("--skip-network", action="store_true", help="Record network targets as unknown without probing sockets/HTTP.")

    def handle(self, *args, **options):
        monitor_options = MonitorOptions(
            web_url=options["web_url"],
            docs_url=options["docs_url"],
            questdb_host=options["questdb_host"],
            questdb_http_port=options["questdb_http_port"],
            questdb_pg_port=options["questdb_pg_port"],
            timeout_seconds=options["timeout"],
            include_network=not options["skip_network"],
            stale_after_seconds=settings.STALE_AFTER_SECONDS,
        )

        def job():
            status = refresh_service_snapshots(
                monitor_service_name=options["service_name"],
                options=monitor_options,
            )
            return "snapshots=%s ok=%s warning=%s error=%s unknown=%s" % (
                status["total_count"],
                status["ok_count"],
                status["warning_count"],
                status["error_count"],
                status["unknown_count"],
            )

        run_worker_heartbeat(
            service_name=options["service_name"],
            interval=options["interval"],
            once=options["once"],
            stdout=self.stdout,
            job_name="refresh_service_snapshots",
            job=job,
        )
