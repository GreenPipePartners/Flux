from pathlib import Path
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import CommandError
from django.core.management import call_command
from django.test import TestCase

from flux.base.models import FieldAgentHeartbeat, FieldDevice, FieldEndpoint, FieldTag

from .field_supervisor import apply_reconciliation_plan, device_endpoint_url, enabled_field_devices, process_spec, reconciliation_plan, write_device_config
from .models import ServeHeartbeat


class ServeSmokeTests(TestCase):
    def test_serve_index_loads(self):
        response = self.client.get("/serve/")

        self.assertEqual(response.status_code, 200)

    def test_flux_worker_once_records_heartbeat(self):
        call_command("flux_worker", "--once", "--service-name", "test-worker")

        self.assertTrue(ServeHeartbeat.objects.filter(service_name="test-worker").exists())


class FieldSupervisorTests(TestCase):
    def setUp(self):
        FieldEndpoint.objects.all().delete()
        self.endpoint = FieldEndpoint.objects.create(
            name="FieldAgent",
            endpoint_url="opc.tcp://0.0.0.0:4840/flux/field",
        )
        self.device = FieldDevice.objects.create(endpoint=self.endpoint, name="Device A", device_type="Simulator")
        FieldTag.objects.create(device=self.device, name="Pressure", data_type=FieldTag.DataType.FLOAT)

    def test_write_device_config_exports_one_endpoint_and_one_device(self):
        with TemporaryDirectory() as temp_dir:
            config_path, endpoint_url, config = write_device_config(
                self.device,
                runtime_dir=Path(temp_dir),
                base_port=4850,
            )

        self.assertIn(str(4850 + self.device.id), endpoint_url)
        self.assertEqual(config["endpoints"][0]["endpoint_url"], endpoint_url)
        self.assertEqual(len(config["endpoints"]), 1)
        self.assertEqual([device["name"] for device in config["endpoints"][0]["devices"]], ["Device A"])
        self.assertTrue(str(config_path).endswith("Device_A.json"))

    def test_write_device_config_preserves_device_delay_metadata(self):
        self.device.config = {
            "source": "sim_device",
            "mode": "slow_network",
            "response_delay_ms": 500,
        }
        self.device.save(update_fields=["config"])

        with TemporaryDirectory() as temp_dir:
            _config_path, _endpoint_url, config = write_device_config(
                self.device,
                runtime_dir=Path(temp_dir),
                base_port=4850,
            )

        device_config = config["endpoints"][0]["devices"][0]
        self.assertEqual(device_config["mode"], "slow_network")
        self.assertEqual(device_config["response_delay_ms"], 500)
        self.assertEqual(device_config["metadata"], self.device.config)

    def test_device_endpoint_url_is_deterministic_per_device(self):
        self.assertEqual(
            device_endpoint_url(self.device, base_port=4850),
            "opc.tcp://0.0.0.0:%s/flux/field/Device_A" % (4850 + self.device.id),
        )

    def test_enabled_field_devices_excludes_disabled_devices_and_endpoints(self):
        disabled_device = FieldDevice.objects.create(
            endpoint=self.endpoint,
            name="Device B",
            device_type="Simulator",
            enabled=False,
        )
        disabled_endpoint = FieldEndpoint.objects.create(name="Disabled Field", enabled=False)
        FieldDevice.objects.create(endpoint=disabled_endpoint, name="Device C", device_type="Simulator")

        devices = list(enabled_field_devices())

        self.assertEqual(devices, [self.device])
        self.assertNotIn(disabled_device, devices)

    def test_process_spec_writes_isolated_config_and_command_per_device(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.device,
                runtime_dir=Path(temp_dir),
                base_port=4900,
                project_path=Path("FieldAgent.csproj"),
            )

            self.assertEqual(spec.key, "field-agent:%s:%s" % (self.endpoint.id, self.device.id))
            self.assertEqual(spec.config_path.name, "Device_A.json")
            self.assertEqual(spec.config_path.parent.name, "FieldAgent")
            self.assertEqual(spec.command[-1], "--FluxField:ConfigPath=%s" % spec.config_path)
            self.assertTrue(spec.config_path.exists())

    def test_reconciliation_keeps_existing_process_instead_of_starting_duplicate(self):
        with TemporaryDirectory() as temp_dir:
            spec = process_spec(
                self.device,
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
                self.device,
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
                self.device,
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
        self.assertEqual(heartbeat.metadata["devices"], ["field-agent:%s:%s" % (self.endpoint.id, self.device.id)])

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
        self.assertEqual(heartbeat.metadata["plan"]["start"], ["field-agent:%s:%s" % (self.endpoint.id, self.device.id)])

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

        agent_heartbeat = FieldAgentHeartbeat.objects.get(instance_id="field-agent:%s:%s" % (self.endpoint.id, self.device.id))
        self.assertIsNone(agent_heartbeat.process_id)
        self.assertEqual(agent_heartbeat.last_error, "exited with status 7")
        supervisor_heartbeat = ServeHeartbeat.objects.get(service_name="flux-field-supervisor")
        self.assertEqual(supervisor_heartbeat.status, ServeHeartbeat.Status.ERROR)

    @patch("flux.serve.management.commands.flux_field_supervisor.enabled_field_devices")
    @patch("flux.serve.management.commands.flux_field_supervisor.start_process")
    def test_field_supervisor_stops_and_marks_disabled_device(self, start_process, enabled_field_devices):
        process = FakeProcess(pid=12345)
        start_process.return_value = process
        enabled_field_devices.side_effect = [[self.device], []]

        with TemporaryDirectory() as temp_dir:
            call_command(
                "flux_field_supervisor",
                "--runtime-dir",
                temp_dir,
                "--project-path",
                "FieldAgent.csproj",
            )

        agent_heartbeat = FieldAgentHeartbeat.objects.get(instance_id="field-agent:%s:%s" % (self.endpoint.id, self.device.id))
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
