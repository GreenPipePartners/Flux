from pathlib import Path
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from flux.base.models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldTag
from dashboard.models import IgnitionBridgeConfig

from .field_supervisor import apply_reconciliation_plan, enabled_field_endpoints, process_spec, reconciliation_plan, server_endpoint_url, write_server_config
from .monitor import MonitorOptions, service_catalog, service_snapshot_status
from .models import ServeCommand, ServeHeartbeat, ServeServiceSnapshot


class ServeSmokeTests(TestCase):
    def test_serve_index_loads(self):
        response = self.client.get("/serve/")

        self.assertEqual(response.status_code, 200)

    def test_serve_index_explains_stale_heartbeats_without_platform_cards(self):
        heartbeat = ServeHeartbeat.objects.create(
            service_name="old-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now() - timezone.timedelta(seconds=300),
        )

        response = self.client.get("/serve/")

        self.assertContains(response, "Raw process heartbeats are retained as evidence")
        self.assertContains(response, "stale")
        self.assertContains(response, "Delete stale heartbeat artifacts")
        self.assertContains(response, f'/serve/heartbeats/{heartbeat.id}/delete/')
        self.assertContains(response, "Entries older than")
        self.assertContains(response, "Recent Logs")
        self.assertNotContains(response, ".NET 10")
        self.assertNotContains(response, "systemd")

    def test_delete_stale_heartbeat_removes_artifact(self):
        heartbeat = ServeHeartbeat.objects.create(
            service_name="old-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now() - timezone.timedelta(seconds=300),
        )

        response = self.client.post(f"/serve/heartbeats/{heartbeat.id}/delete/")

        self.assertRedirects(response, "/serve/")
        self.assertFalse(ServeHeartbeat.objects.filter(id=heartbeat.id).exists())

    def test_delete_fresh_running_heartbeat_is_blocked(self):
        heartbeat = ServeHeartbeat.objects.create(
            service_name="worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now(),
        )

        response = self.client.post(f"/serve/heartbeats/{heartbeat.id}/delete/")

        self.assertRedirects(response, "/serve/")
        self.assertTrue(ServeHeartbeat.objects.filter(id=heartbeat.id).exists())

    def test_delete_stale_heartbeats_removes_only_stale_artifacts(self):
        stale = ServeHeartbeat.objects.create(
            service_name="old-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now() - timezone.timedelta(seconds=300),
        )
        fresh = ServeHeartbeat.objects.create(
            service_name="fresh-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now(),
        )

        response = self.client.post("/serve/heartbeats/delete-stale/")

        self.assertRedirects(response, "/serve/")
        self.assertFalse(ServeHeartbeat.objects.filter(id=stale.id).exists())
        self.assertTrue(ServeHeartbeat.objects.filter(id=fresh.id).exists())

    def test_flux_worker_once_records_heartbeat(self):
        call_command("flux_worker", "--once", "--service-name", "test-worker")

        self.assertTrue(ServeHeartbeat.objects.filter(service_name="test-worker").exists())

    def test_serve_index_renders_service_snapshots(self):
        ServeServiceSnapshot.objects.create(
            service_key="Flux.web.server",
            display_name="Flux Web Server",
            category="Web",
            desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary="HTTP 200",
        )

        response = self.client.get("/serve/")

        self.assertContains(response, "Observed Service Health")
        self.assertContains(response, "Flux.web.server")
        self.assertContains(response, "HTTP 200")
        self.assertContains(response, "1/1 services healthy")

    def test_flux_serve_monitor_once_records_expected_service_snapshots(self):
        ServeHeartbeat.objects.create(
            service_name="flux-field-supervisor",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            current_job="supervising field agents",
            last_seen_at=timezone.now(),
        )

        call_command("flux_serve_monitor", "--once", "--skip-network")

        snapshots = {snapshot.service_key: snapshot for snapshot in ServeServiceSnapshot.objects.all()}
        self.assertEqual(snapshots["Flux.serve.monitor"].observed_state, ServeServiceSnapshot.ObservedState.HEALTHY)
        self.assertEqual(snapshots["Flux.serve.field-supervisor"].observed_state, ServeServiceSnapshot.ObservedState.HEALTHY)
        self.assertEqual(snapshots["Flux.web.server"].observed_state, ServeServiceSnapshot.ObservedState.UNKNOWN)
        self.assertEqual(snapshots["Flux.web.docs"].summary, "Network probe skipped.")
        self.assertEqual(snapshots["Flux.plane.qdb"].observed_state, ServeServiceSnapshot.ObservedState.UNKNOWN)

    def test_flux_serve_monitor_records_field_agent_endpoint_snapshot(self):
        endpoint = FieldEndpoint.objects.create(name="sir-fluxolot-fishtank", enabled=True, status=FieldEndpoint.Status.RUNNING)
        device = FieldDevice.objects.create(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        FieldTag.objects.create(device=device, name="TANK_TEMPERATURE", data_type=FieldTag.DataType.FLOAT)
        FieldAgentHeartbeat.objects.create(endpoint=endpoint, instance_id="field-agent:%s" % endpoint.id, last_seen_at=timezone.now())

        call_command("flux_serve_monitor", "--once", "--skip-network")

        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.serve.field-agent:sir-fluxolot-fishtank")
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.HEALTHY)
        self.assertEqual(snapshot.severity, ServeServiceSnapshot.Severity.OK)

    def test_flux_serve_monitor_marks_absent_field_agent_snapshot_stopped(self):
        ServeServiceSnapshot.objects.create(
            service_key="Flux.serve.field-agent:old-endpoint",
            display_name="FieldAgent old-endpoint",
            category="Field runtime",
            desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary="Previously healthy",
        )

        call_command("flux_serve_monitor", "--once", "--skip-network")

        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.serve.field-agent:old-endpoint")
        self.assertEqual(snapshot.desired_state, ServeServiceSnapshot.DesiredState.DISABLED)
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.STOPPED)
        self.assertEqual(snapshot.summary, "Service is disabled or no longer configured.")

    def test_service_catalog_includes_static_dynamic_and_bridge_services(self):
        endpoint = FieldEndpoint.objects.create(name="sir-fluxolot-fishtank", enabled=True, status=FieldEndpoint.Status.RUNNING)
        device = FieldDevice.objects.create(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        FieldTag.objects.create(device=device, name="TANK_TEMPERATURE", data_type=FieldTag.DataType.FLOAT)
        IgnitionBridgeConfig.objects.create(name="simulator", base_url="http://localhost:8088/system/webdev/flux")

        definitions = service_catalog(options=MonitorOptions(include_network=False), monitor_service_name="flux-serve-monitor")
        keys = {definition.service_key for definition in definitions}

        self.assertIn("Flux.serve.monitor", keys)
        self.assertIn("Flux.web.server", keys)
        self.assertIn("Flux.serve.field-agent:sir-fluxolot-fishtank", keys)
        self.assertIn("Flux.bridge:simulator", keys)

    def test_service_snapshot_status_marks_old_snapshots_stale_without_mutating_row(self):
        snapshot = ServeServiceSnapshot.objects.create(
            service_key="Flux.web.server",
            display_name="Flux Web Server",
            category="Web",
            desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            last_checked_at=timezone.now() - timezone.timedelta(seconds=300),
            summary="HTTP 200",
        )

        status = service_snapshot_status([snapshot], stale_after_seconds=120)

        self.assertEqual(status["state"], "warning")
        self.assertEqual(status["warning_count"], 1)
        self.assertEqual(status["stale_count"], 1)
        self.assertEqual(status["items"][0]["observed_state"], ServeServiceSnapshot.ObservedState.STALE)
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.HEALTHY)


class FieldSupervisorTests(TestCase):
    def setUp(self):
        FieldEndpoint.objects.all().delete()
        self.endpoint = FieldEndpoint.objects.create(
            name="FieldAgent",
            endpoint_url="opc.tcp://0.0.0.0:4840/flux/field",
        )
        self.device = FieldDevice.objects.create(endpoint=self.endpoint, name="Device A", device_type="Simulator")
        FieldTag.objects.create(device=self.device, name="Pressure", data_type=FieldTag.DataType.FLOAT)
        self.second_device = FieldDevice.objects.create(endpoint=self.endpoint, name="Device B", device_type="Simulator")
        FieldTag.objects.create(device=self.second_device, name="Temperature", data_type=FieldTag.DataType.FLOAT)

    def test_write_server_config_exports_one_endpoint_with_many_devices(self):
        with TemporaryDirectory() as temp_dir:
            config_path, endpoint_url, config = write_server_config(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4850,
            )

        self.assertIn(str(4850 + self.endpoint.id), endpoint_url)
        self.assertEqual(config["endpoints"][0]["endpoint_url"], endpoint_url)
        self.assertEqual(len(config["endpoints"]), 1)
        self.assertEqual([device["name"] for device in config["endpoints"][0]["devices"]], ["Device A", "Device B"])
        self.assertTrue(str(config_path).endswith("FieldAgent.json"))

    def test_write_server_config_preserves_device_delay_metadata(self):
        self.device.config = {
            "source": "sim_device",
            "mode": "slow_network",
            "response_delay_ms": 500,
        }
        self.device.save(update_fields=["config"])

        with TemporaryDirectory() as temp_dir:
            _config_path, _endpoint_url, config = write_server_config(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4850,
            )

        device_config = config["endpoints"][0]["devices"][0]
        self.assertEqual(device_config["mode"], "slow_network")
        self.assertEqual(device_config["response_delay_ms"], 500)
        self.assertEqual(device_config["metadata"], self.device.config)

    def test_server_endpoint_url_is_deterministic_per_endpoint(self):
        self.assertEqual(
            server_endpoint_url(self.endpoint, base_port=4850),
            "opc.tcp://0.0.0.0:%s/flux/sim/FieldAgent" % (4850 + self.endpoint.id),
        )

    def test_server_endpoint_url_allows_local_bind_host(self):
        self.assertEqual(
            server_endpoint_url(self.endpoint, base_port=4850, host="localhost"),
            "opc.tcp://localhost:%s/flux/sim/FieldAgent" % (4850 + self.endpoint.id),
        )

    def test_enabled_field_endpoints_excludes_disabled_endpoints_and_empty_endpoints(self):
        disabled_endpoint = FieldEndpoint.objects.create(name="Disabled Field", enabled=False)
        FieldDevice.objects.create(endpoint=disabled_endpoint, name="Device C", device_type="Simulator")
        empty_endpoint = FieldEndpoint.objects.create(name="Empty Field", enabled=True)

        endpoints = list(enabled_field_endpoints())

        self.assertEqual(endpoints, [self.endpoint])
        self.assertNotIn(disabled_endpoint, endpoints)
        self.assertNotIn(empty_endpoint, endpoints)

    def test_process_spec_writes_isolated_config_and_command_per_server(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4900,
                project_path=Path("FieldAgent.csproj"),
            )

            self.assertEqual(spec.key, "field-agent:%s" % self.endpoint.id)
            self.assertEqual(spec.config_path.name, "FieldAgent.json")
            self.assertEqual(spec.command[-1], "--FluxField:ConfigPath=%s" % spec.config_path)
            self.assertTrue(spec.config_path.exists())

    def test_reconciliation_keeps_existing_process_instead_of_starting_duplicate(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4900,
                project_path=Path("FieldAgent.csproj"),
            )
        process = FakeProcess(pid=100)

        plan = reconciliation_plan([spec], {spec.key: process})
        processes = apply_reconciliation_plan(plan, {spec.key: process}, start=lambda spec: FakeProcess(pid=200))

        self.assertEqual(plan.keep_keys, [spec.key])
        self.assertEqual(plan.start_keys, [])
        self.assertEqual(processes[spec.key], process)

    def test_reconciliation_stops_process_for_disabled_device(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4900,
                project_path=Path("FieldAgent.csproj"),
            )
        process = FakeProcess(pid=100)

        plan = reconciliation_plan([], {spec.key: process})
        processes = apply_reconciliation_plan(plan, {spec.key: process}, start=lambda spec: FakeProcess(pid=200))

        self.assertEqual(plan.stop_keys, [spec.key])
        self.assertTrue(process.terminated)
        self.assertEqual(processes, {})

    def test_reconciliation_records_failed_process_without_restart_in_same_plan(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4900,
                project_path=Path("FieldAgent.csproj"),
            )
        process = FakeProcess(pid=100, exit_code=7)

        plan = reconciliation_plan([spec], {spec.key: process})

        self.assertEqual(plan.failed, {spec.key: 7})
        self.assertEqual(plan.start_keys, [])

    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_once_records_heartbeat_and_starts_process(self, start_process):
        start_process.return_value = FakeProcess(pid=12345)
        with TemporaryDirectory() as temp_dir:
            call_command(
                "flux_field_supervisor",
                "--once",
                "--runtime-dir",
                temp_dir,
                "--project-path",
                "FieldAgent.csproj",
            )

        start_process.assert_called_once()
        heartbeat = ServeHeartbeat.objects.get(service_name="flux-field-supervisor")
        self.assertEqual(heartbeat.metadata["servers"], ["field-agent:%s" % self.endpoint.id])

    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_once_processes_requested_start_command(self, start_process):
        start_process.return_value = FakeProcess(pid=12345)
        self.endpoint.enabled = False
        self.endpoint.status = FieldEndpoint.Status.DISABLED
        self.endpoint.save(update_fields=["enabled", "status"])
        command = ServeCommand.objects.create(command="start_sim_server", payload={"endpoint_id": self.endpoint.id})

        with TemporaryDirectory() as temp_dir:
            call_command(
                "flux_field_supervisor",
                "--once",
                "--runtime-dir",
                temp_dir,
                "--project-path",
                "FieldAgent.csproj",
            )

        command.refresh_from_db()
        self.endpoint.refresh_from_db()
        start_process.assert_called_once()
        self.assertEqual(command.status, ServeCommand.Status.COMPLETED)
        self.assertTrue(self.endpoint.enabled)
        self.assertEqual(self.endpoint.status, FieldEndpoint.Status.RUNNING)

    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_once_processes_requested_stop_command(self, start_process):
        self.endpoint.enabled = True
        self.endpoint.status = FieldEndpoint.Status.RUNNING
        self.endpoint.save(update_fields=["enabled", "status"])
        command = ServeCommand.objects.create(command="stop_sim_server", payload={"endpoint_id": self.endpoint.id})

        with TemporaryDirectory() as temp_dir:
            call_command(
                "flux_field_supervisor",
                "--once",
                "--runtime-dir",
                temp_dir,
                "--project-path",
                "FieldAgent.csproj",
            )

        command.refresh_from_db()
        self.endpoint.refresh_from_db()
        start_process.assert_not_called()
        self.assertEqual(command.status, ServeCommand.Status.COMPLETED)
        self.assertFalse(self.endpoint.enabled)
        self.assertEqual(self.endpoint.status, FieldEndpoint.Status.DISABLED)

    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_dry_run_outputs_plan_without_starting_process(self, start_process):
        out = StringIO()
        with TemporaryDirectory() as temp_dir:
            call_command(
                "flux_field_supervisor",
                "--dry-run",
                "--runtime-dir",
                temp_dir,
                "--project-path",
                "FieldAgent.csproj",
                stdout=out,
            )

        start_process.assert_not_called()
        self.assertIn('"start": [', out.getvalue())
        heartbeat = ServeHeartbeat.objects.get(service_name="flux-field-supervisor")
        self.assertEqual(heartbeat.metadata["plan"]["start"], ["field-agent:%s" % self.endpoint.id])

    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_records_failed_process_status(self, start_process):
        start_process.return_value = FakeProcess(pid=12345, exit_code=7)

        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(CommandError):
                call_command(
                    "flux_field_supervisor",
                    "--runtime-dir",
                    temp_dir,
                    "--project-path",
                    "FieldAgent.csproj",
                )

        agent_heartbeat = FieldAgentHeartbeat.objects.get(instance_id="field-agent:%s" % self.endpoint.id)
        self.assertIsNone(agent_heartbeat.process_id)
        self.assertEqual(agent_heartbeat.last_error, "exited with status 7")
        supervisor_heartbeat = ServeHeartbeat.objects.get(service_name="flux-field-supervisor")
        self.assertEqual(supervisor_heartbeat.status, ServeHeartbeat.Status.ERROR)

    @patch("flux.serve.management.commands.flux_field_supervisor.enabled_field_endpoints")
    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_stops_and_marks_disabled_server(self, start_process, enabled_field_endpoints):
        process = FakeProcess(pid=12345)
        start_process.return_value = process
        enabled_field_endpoints.side_effect = [[self.endpoint], []]

        with TemporaryDirectory() as temp_dir:
            call_command(
                "flux_field_supervisor",
                "--runtime-dir",
                temp_dir,
                "--project-path",
                "FieldAgent.csproj",
                "--exit-when-idle",
            )

        agent_heartbeat = FieldAgentHeartbeat.objects.get(instance_id="field-agent:%s" % self.endpoint.id)
        self.assertTrue(process.terminated)
        self.assertIsNone(agent_heartbeat.process_id)
        self.assertEqual(agent_heartbeat.last_error, "disabled or no longer configured")


class FakeProcess:
    def __init__(self, *, pid, exit_code=None):
        self.pid = pid
        self.exit_code = exit_code
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = 0

    def wait(self, timeout=None):
        return self.exit_code or 0

    def kill(self):
        self.killed = True
        self.exit_code = -9
