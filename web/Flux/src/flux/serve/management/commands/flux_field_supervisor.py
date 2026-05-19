import json
from pathlib import Path
import signal
import subprocess
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from flux.base.models import FieldAgentHeartbeat
from flux.serve.field_supervisor import apply_reconciliation_plan, enabled_field_devices, process_spec, reconciliation_plan, start_process
from flux.serve.models import ServeHeartbeat


class Command(BaseCommand):
    help = "Run one FieldAgent OPC-UA server process per enabled field device."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--base-port", type=int, default=4850)
        parser.add_argument("--runtime-dir", default=str(settings.BASE_DIR.parents[1] / ".runtime" / "field-agent"))
        parser.add_argument("--project-path", default=str(settings.BASE_DIR.parents[1] / "field" / "Flux.FieldAgent" / "Flux.FieldAgent.csproj"))
        parser.add_argument("--service-name", default="flux-field-supervisor")

    def handle(self, *args, **options):
        runtime_dir = Path(options["runtime_dir"])
        project_path = Path(options["project_path"])
        specs = self.process_specs(runtime_dir=runtime_dir, base_port=options["base_port"], project_path=project_path)
        processes = {}
        plan = reconciliation_plan(specs, processes)
        if not options["dry_run"]:
            apply_reconciliation_plan(plan, processes, start=start_process)
        heartbeat = ServeHeartbeat.objects.update_or_create(
            service_name=options["service_name"],
            instance_id="default",
            defaults={
                "status": ServeHeartbeat.Status.RUNNING,
                "last_seen_at": timezone.now(),
                "current_job": "devices=%s running=%s" % (len(specs), len(processes)),
                "metadata": {"devices": [spec.key for spec in specs], "dry_run": options["dry_run"], "plan": plan.as_dict()},
            },
        )[0]
        for spec in specs:
            process = processes.get(spec.key)
            if process is not None:
                self.record_process_status(spec, process_id=process.pid, last_error="")
        self.stdout.write("%s: %s" % (heartbeat.service_name, heartbeat.current_job))
        if options["dry_run"]:
            self.stdout.write(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
        if options["once"] or options["dry_run"]:
            return
        stop_requested = False
        failed_exit_code = None

        def request_stop(signum, frame):
            nonlocal stop_requested
            stop_requested = True

        previous_sigterm = signal.signal(signal.SIGTERM, request_stop)
        previous_sigint = signal.signal(signal.SIGINT, request_stop)
        try:
            while not stop_requested:
                specs = self.process_specs(runtime_dir=runtime_dir, base_port=options["base_port"], project_path=project_path)
                spec_by_key = {spec.key: spec for spec in specs}
                plan = reconciliation_plan(specs, processes)
                for key, exit_code in plan.failed.items():
                    self.stderr.write("FieldAgent process %s exited with status %s" % (key, exit_code))
                    spec = spec_by_key.get(key)
                    if spec is not None:
                        self.record_process_status(spec, process_id=None, last_error="exited with status %s" % exit_code)
                    else:
                        FieldAgentHeartbeat.objects.filter(instance_id=key).update(
                            process_id=None,
                            last_seen_at=timezone.now(),
                            last_error="exited with status %s" % exit_code,
                        )
                    if exit_code != 0:
                        failed_exit_code = exit_code
                        stop_requested = True
                for key in plan.stop_keys:
                    FieldAgentHeartbeat.objects.filter(instance_id=key).update(
                        process_id=None,
                        last_seen_at=timezone.now(),
                        last_error="disabled or no longer configured",
                    )
                apply_reconciliation_plan(plan, processes, start=start_process)
                for spec in specs:
                    process = processes.get(spec.key)
                    if process is not None:
                        self.record_process_status(spec, process_id=process.pid, last_error="")
                ServeHeartbeat.objects.filter(pk=heartbeat.pk).update(
                    status=ServeHeartbeat.Status.ERROR if failed_exit_code is not None else ServeHeartbeat.Status.RUNNING,
                    last_seen_at=timezone.now(),
                    current_job="devices=%s running=%s" % (len(specs), len(processes)),
                    last_error="FieldAgent process exited with status %s" % failed_exit_code if failed_exit_code is not None else "",
                    metadata={"devices": [spec.key for spec in specs], "dry_run": False, "plan": plan.as_dict()},
                )
                if processes and not stop_requested:
                    time.sleep(1)
                if not processes:
                    stop_requested = True
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            signal.signal(signal.SIGINT, previous_sigint)
            for process in processes.values():
                if process.poll() is None:
                    process.terminate()
            for process in processes.values():
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        if stop_requested:
            self.stdout.write("Stopped FieldAgent supervisor.")
        if failed_exit_code is not None:
            raise CommandError("FieldAgent process exited with status %s" % failed_exit_code)

    def process_specs(self, *, runtime_dir, base_port, project_path):
        return [
            process_spec(device, runtime_dir=runtime_dir, base_port=base_port, project_path=project_path)
            for device in enabled_field_devices()
        ]

    def record_process_status(self, spec, *, process_id, last_error):
        FieldAgentHeartbeat.objects.update_or_create(
            endpoint=spec.device.endpoint,
            instance_id=spec.key,
            defaults={
                "process_id": process_id,
                "last_seen_at": timezone.now(),
                "current_node_count": spec.device.tags.filter(enabled=True).count(),
                "last_error": last_error,
            },
        )
