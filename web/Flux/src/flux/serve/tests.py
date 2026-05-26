import os
from dataclasses import replace
from pathlib import Path
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from flux.base.models import Tag
from flux.serve.models import FieldAgentHeartbeat
from flux.sim.models import FieldEndpoint
from flux.bridge.models import IgnitionBridgeConfig
from flux.bridge.services import BridgeProbeResult

from .field_supervisor import apply_reconciliation_plan, enabled_field_endpoints, process_spec, reconciliation_plan, server_endpoint_url, write_server_config
from .monitor import MonitorOptions, refresh_service_snapshots, service_catalog, service_snapshot_status
from .models import ServeCommand, ServeHeartbeat, ServeServiceSnapshot
from flux.sim.testing import create_device_config, create_tag_config


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

    def test_serve_heartbeat_table_uses_ten_row_server_side_htmx_pagination(self):
        now = timezone.now()
        for index in range(12):
            ServeHeartbeat.objects.create(
                service_name=f"worker-{index:02d}",
                instance_id="default",
                status=ServeHeartbeat.Status.RUNNING,
                last_seen_at=now,
            )

        first_page = self.client.get("/serve/", {"card": "serve-platform", "mode": "detail"})
        second_page = self.client.get(
            "/serve/",
            {"card": "serve-platform", "mode": "detail", "heartbeats_page": "2"},
        )

        self.assertContains(first_page, "Showing 1-10 of 12 heartbeats")
        self.assertContains(first_page, 'hx-target="#serve-platform-comp-card"')
        self.assertContains(first_page, "heartbeats_page=2")
        self.assertEqual(
            [item["heartbeat"].service_name for item in first_page.context["serve_status"]["items"]],
            [f"worker-{index:02d}" for index in range(10)],
        )
        self.assertContains(second_page, "Showing 11-12 of 12 heartbeats")
        self.assertContains(second_page, "heartbeats_page=1")
        self.assertEqual(
            [item["heartbeat"].service_name for item in second_page.context["serve_status"]["items"]],
            ["worker-10", "worker-11"],
        )

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

        heartbeat = ServeHeartbeat.objects.get(service_name="test-worker")
        self.assertEqual(heartbeat.platform, ServeHeartbeat.Platform.LINUX)

    def test_flux_worker_rejects_non_linux_platform(self):
        with patch("platform.system", return_value="Darwin"):
            with self.assertRaisesMessage(RuntimeError, "Flux workers require Linux"):
                call_command("flux_worker", "--once", "--service-name", "bad-worker")

        self.assertFalse(ServeHeartbeat.objects.filter(service_name="bad-worker").exists())

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
        endpoint = FieldEndpoint.objects.create(
            name="sir-fluxolot-fishtank",
            endpoint_url="opc.tcp://localhost:5061/flux/field",
            enabled=True,
            status=FieldEndpoint.Status.RUNNING,
        )
        device = create_device_config(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        create_tag_config(device=device, name="TANK_TEMPERATURE", data_type=Tag.DataType.FLOAT, materialized=True)
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:%s" % endpoint.id,
            process_id=os.getpid(),
            last_seen_at=timezone.now(),
        )

        with patch("flux.serve.monitor.tcp_available", return_value=(True, "")):
            refresh_service_snapshots(options=MonitorOptions(timeout_seconds=0.01))

        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.serve.field-agent:sir-fluxolot-fishtank")
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.HEALTHY)
        self.assertEqual(snapshot.severity, ServeServiceSnapshot.Severity.OK)
        self.assertTrue(snapshot.metadata["process_alive"])
        self.assertTrue(snapshot.metadata["tcp_ok"])
        self.assertEqual(snapshot.metadata["port"], 5061)

    def test_flux_serve_monitor_rejects_dead_field_agent_process(self):
        endpoint = FieldEndpoint.objects.create(
            name="sir-fluxolot-fishtank",
            endpoint_url="opc.tcp://localhost:5061/flux/field",
            enabled=True,
            status=FieldEndpoint.Status.RUNNING,
        )
        device = create_device_config(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        create_tag_config(device=device, name="TANK_TEMPERATURE", data_type=Tag.DataType.FLOAT, materialized=True)
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:%s" % endpoint.id,
            process_id=987654,
            last_seen_at=timezone.now(),
        )

        with patch("flux.serve.monitor.process_id_is_alive", return_value=(False, "Process 987654 does not exist.")):
            refresh_service_snapshots(options=MonitorOptions(include_network=False))

        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.serve.field-agent:sir-fluxolot-fishtank")
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.ERROR)
        self.assertEqual(snapshot.severity, ServeServiceSnapshot.Severity.ERROR)
        self.assertEqual(snapshot.summary, "FieldAgent process is not alive.")
        self.assertFalse(snapshot.metadata["process_alive"])

    def test_flux_serve_monitor_rejects_closed_field_agent_tcp_port(self):
        endpoint = FieldEndpoint.objects.create(
            name="sir-fluxolot-fishtank",
            endpoint_url="opc.tcp://0.0.0.0:5061/flux/field",
            enabled=True,
            status=FieldEndpoint.Status.RUNNING,
        )
        device = create_device_config(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        create_tag_config(device=device, name="TANK_TEMPERATURE", data_type=Tag.DataType.FLOAT, materialized=True)
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:%s" % endpoint.id,
            process_id=os.getpid(),
            last_seen_at=timezone.now(),
        )

        with patch("flux.serve.monitor.tcp_available", return_value=(False, "connection refused")):
            refresh_service_snapshots(options=MonitorOptions(timeout_seconds=0.01))

        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.serve.field-agent:sir-fluxolot-fishtank")
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.ERROR)
        self.assertEqual(snapshot.severity, ServeServiceSnapshot.Severity.ERROR)
        self.assertEqual(snapshot.summary, "FieldAgent TCP port is not reachable.")
        self.assertEqual(snapshot.last_error, "connection refused")
        self.assertEqual(snapshot.metadata["tcp_host"], "localhost")
        self.assertFalse(snapshot.metadata["tcp_ok"])

    def test_flux_serve_monitor_degrades_field_agent_when_tcp_probe_is_skipped(self):
        endpoint = FieldEndpoint.objects.create(
            name="sir-fluxolot-fishtank",
            endpoint_url="opc.tcp://localhost:5061/flux/field",
            enabled=True,
            status=FieldEndpoint.Status.RUNNING,
        )
        device = create_device_config(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        create_tag_config(device=device, name="TANK_TEMPERATURE", data_type=Tag.DataType.FLOAT, materialized=True)
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:%s" % endpoint.id,
            process_id=os.getpid(),
            last_seen_at=timezone.now(),
        )

        refresh_service_snapshots(options=MonitorOptions(include_network=False))

        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.serve.field-agent:sir-fluxolot-fishtank")
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.DEGRADED)
        self.assertEqual(snapshot.severity, ServeServiceSnapshot.Severity.WARNING)
        self.assertEqual(snapshot.summary, "FieldAgent process is alive; TCP probe skipped.")
        self.assertEqual(snapshot.metadata["tcp_probe"], "skipped")

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
        device = create_device_config(endpoint=endpoint, name="Sir-Fluxolot-Fishtank", device_type="Simulator")
        create_tag_config(device=device, name="TANK_TEMPERATURE", data_type=Tag.DataType.FLOAT, materialized=True)
        IgnitionBridgeConfig.objects.create(name="simulator", base_url="http://localhost:8088/system/webdev/flux")

        definitions = service_catalog(options=MonitorOptions(include_network=False), monitor_service_name="flux-serve-monitor")
        keys = {definition.service_key for definition in definitions}

        self.assertIn("Flux.serve.monitor", keys)
        self.assertIn("Flux.web.server", keys)
        self.assertIn("Flux.serve.field-agent:sir-fluxolot-fishtank", keys)
        self.assertIn("Flux.bridge:simulator", keys)

    def test_bridge_snapshot_refreshes_bridge_probe_and_latest_config_status(self):
        config = IgnitionBridgeConfig.objects.create(name="simulator", base_url="http://localhost:8088/system/webdev/flux")
        checked_at = timezone.now()

        with patch(
            "flux.serve.monitor.probe_bridge",
            return_value=BridgeProbeResult(
                ok=True,
                message="Connected to Ignition 8.3.",
                checked_at=checked_at,
                version="8.3",
            ),
        ) as probe_bridge:
            refresh_service_snapshots(options=MonitorOptions(include_network=True, timeout_seconds=0.01))

        config.refresh_from_db()
        snapshot = ServeServiceSnapshot.objects.get(service_key="Flux.bridge:simulator")
        probe_bridge.assert_called_once()
        self.assertTrue(config.last_test_ok)
        self.assertEqual(config.last_test_message, "Connected to Ignition 8.3.")
        self.assertEqual(snapshot.observed_state, ServeServiceSnapshot.ObservedState.HEALTHY)
        self.assertEqual(snapshot.metadata["probe"], "fluxy_version")
        self.assertEqual(snapshot.metadata["version"], "8.3")

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
        self.device = create_device_config(endpoint=self.endpoint, name="Device A", device_type="Simulator")
        create_tag_config(device=self.device, name="Pressure", data_type=Tag.DataType.FLOAT, materialized=True)
        self.second_device = create_device_config(endpoint=self.endpoint, name="Device B", device_type="Simulator")
        create_tag_config(device=self.second_device, name="Temperature", data_type=Tag.DataType.FLOAT, materialized=True)

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
            "opc.tcp://localhost:%s/flux/sim/FieldAgent" % (4850 + self.endpoint.id),
        )

    def test_server_endpoint_url_allows_explicit_host(self):
        self.assertEqual(
            server_endpoint_url(self.endpoint, base_port=4850, host="192.0.2.10"),
            "opc.tcp://192.0.2.10:%s/flux/sim/FieldAgent" % (4850 + self.endpoint.id),
        )

    def test_enabled_field_endpoints_excludes_disabled_endpoints_and_empty_endpoints(self):
        disabled_endpoint = FieldEndpoint.objects.create(name="Disabled Field", enabled=False)
        create_device_config(endpoint=disabled_endpoint, name="Device C", device_type="Simulator")
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
            self.assertIn("--FluxField:ConfigPath=%s" % spec.config_path, spec.command)
            self.assertIn(
                "--FluxField:CertificateStorePath=%s" % (Path(temp_dir) / "pki" / "FieldAgent"),
                spec.command,
            )
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

    def test_reconciliation_restarts_process_when_config_changes(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.endpoint,
                runtime_dir=Path(temp_dir),
                base_port=4900,
                project_path=Path("FieldAgent.csproj"),
            )
        old_spec = replace(spec, config_hash="old-config")
        process = FakeProcess(pid=100)

        plan = reconciliation_plan([spec], {spec.key: process}, {spec.key: old_spec})
        processes = apply_reconciliation_plan(plan, {spec.key: process}, start=lambda spec: FakeProcess(pid=200))

        self.assertEqual(plan.stop_keys, [spec.key])
        self.assertEqual(plan.start_keys, [spec.key])
        self.assertTrue(process.terminated)
        self.assertEqual(processes[spec.key].pid, 200)

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
        self.assertIn("opc.tcp://localhost:", start_process.call_args.args[0].endpoint_url)
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.endpoint_url, start_process.call_args.args[0].endpoint_url)
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
