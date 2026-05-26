from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from io import StringIO
from unittest.mock import ANY, patch

from .copy_context import render_bridge_llm_markdown, render_bridge_table_markdown
from flux.bridge.models import IgnitionBridgeConfig
from .services import dashboard_readiness, dashboard_runtime_state, excluded_interface_runtime_tag_count, field_device_status, interface_runtime_tags, serve_status, start_sim_server, stop_sim_server

from flux.base.models import Tag
from flux.serve.models import FieldAgentHeartbeat
from flux.sim.models import FieldEndpoint
from flux.base.runtime import LatestTagValue, RuntimeTag, TagSchedule
from flux.spot.models import LiveScope
from flux.opt.models import RefreshLane
from flux.serve.models import ServeCommand, ServeHeartbeat, ServeServiceSnapshot
from flux.trace.models import TraceProfile
from flux.sim.testing import create_device_config, create_tag_config


class InitialSetupTests(TestCase):
    def test_home_redirects_to_setup_when_no_users_exist(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertRedirects(response, reverse("dashboard:setup"))

    def test_setup_creates_initial_superuser(self):
        response = self.client.post(
            reverse("dashboard:setup"),
            {
                "username": "admin",
                "email": "admin@example.com",
                "password1": "long-test-password-123",
                "password2": "long-test-password-123",
            },
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        user = get_user_model().objects.get(username="admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_setup_redirects_when_user_already_exists(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")

        response = self.client.get(reverse("dashboard:setup"))

        self.assertRedirects(response, reverse("dashboard:home"))


class DashboardStaticAssetTests(SimpleTestCase):
    def test_site_js_guards_flux_web_display_pulse(self):
        site_js = (settings.BASE_DIR / "src" / "static" / "flux" / "site.js").read_text()

        self.assertIn("function fluxDisplayPulseCanRun", site_js)
        self.assertIn("window.fluxDisplayPulseCanRun = fluxDisplayPulseCanRun", site_js)
        self.assertIn('data-comp-mode="configure"', site_js)
        self.assertIn('form[data-flux-pulse-dirty="1"]', site_js)
        self.assertIn("htmx:configRequest", site_js)
        self.assertIn("mergeCurrentQueryPath", site_js)
        self.assertIn(".comp-card-mode-control", site_js)
        self.assertIn("remainingExact", site_js)
        self.assertIn("Math.floor(remainingExact)", site_js)

    def test_local_htmx_supports_filtered_every_triggers(self):
        htmx_js = (settings.BASE_DIR / "src" / "static" / "flux" / "vendor" / "htmx" / "htmx.min.js").read_text()

        self.assertIn("splitEveryTriggerSpec", htmx_js)
        self.assertIn("triggerConditionPasses", htmx_js)
        self.assertIn("fluxDisplayPulseCanRun()", htmx_js)

    def test_local_htmx_configures_polling_requests_from_current_url(self):
        htmx_js = (settings.BASE_DIR / "src" / "static" / "flux" / "vendor" / "htmx" / "htmx.min.js").read_text()

        self.assertIn("htmx:configRequest", htmx_js)
        self.assertIn("config.path", htmx_js)
        self.assertIn("push === 'false'", htmx_js)

    def test_site_js_keeps_table_copy_without_client_side_pagination(self):
        site_js = (settings.BASE_DIR / "src" / "static" / "flux" / "site.js").read_text()

        self.assertIn("Copy table contents", site_js)
        self.assertIn("function initializeCopyableTables", site_js)
        self.assertNotIn("function initializeTablePagination", site_js)
        self.assertNotIn("data-table-pagination-action", site_js)
        self.assertNotIn("tablePaginationHidden", site_js)

    def test_site_js_treats_fluxolot_scope_as_preview_placeholder(self):
        site_js = (settings.BASE_DIR / "src" / "static" / "flux" / "site.js").read_text()

        self.assertIn("function initializePreviewDefaultInputs", site_js)
        self.assertIn('input[name="live_scope"]', site_js)
        self.assertIn('input.value === "Fluxolot"', site_js)
        self.assertIn('input.value = ""', site_js)

    def test_site_css_styles_table_pagination_controls(self):
        site_css = (settings.BASE_DIR / "src" / "static" / "flux" / "site.css").read_text()

        self.assertIn(".stale-list { border: 1px", site_css)
        self.assertIn(".stale-row:first-child { border-top: 0; }", site_css)
        self.assertIn(".table-pagination-controls", site_css)
        self.assertIn(".table-pagination-summary", site_css)
        self.assertIn(".table-pagination-disabled", site_css)
        self.assertIn(".flux-web-pulse-timer", site_css)
        self.assertIn(".flux-web-pulse-track", site_css)
        self.assertIn("--pulse-countdown-percent", site_css)


class FluxWebPulseContextTests(SimpleTestCase):
    def test_display_pulse_context_marks_old_cached_state_stale(self):
        from flux.web_pulse import display_pulse_context

        context = display_pulse_context(
            source_label="Flux.storage",
            last_backend_at=timezone.now() - timezone.timedelta(seconds=settings.STALE_AFTER_SECONDS + 5),
            state="ok",
            detail="cached state",
        )

        self.assertEqual(context["refresh_seconds"], 5)
        self.assertEqual(context["state"], "stale")
        self.assertEqual(context["state_label"], "Stale")


class DashboardBridgeTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")

    def test_home_renders_bridge_without_token_value(self):
        IgnitionBridgeConfig.objects.create(
            name="prod",
            role=IgnitionBridgeConfig.Role.PRODUCTION,
            base_url="http://prod.example.test/system/webdev/flux",
            token="secret-token",
        )
        IgnitionBridgeConfig.objects.create(
            name="sim",
            role=IgnitionBridgeConfig.Role.SIMULATOR,
            base_url="http://sim.example.test/system/webdev/flux",
        )

        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "Control Workbench")
        self.assertContains(response, "Command Center")
        self.assertContains(response, "Flux.bridge")
        self.assertContains(response, "1 Production")
        self.assertContains(response, "1 Simulated")
        self.assertContains(response, "Flux.mine")
        self.assertContains(response, "0 PLCs Mined")
        self.assertContains(response, "0 HMI&#x27;s mined")
        self.assertContains(response, "Flux.build")
        self.assertContains(response, "0 cells built")
        self.assertNotContains(response, "Open live view")
        self.assertNotContains(response, '<a class="button button-secondary" href="/serve/">Serve status</a>', html=True)
        self.assertNotContains(response, "Configure tags")
        self.assertNotContains(response, ">Nav<")
        self.assertNotContains(response, ">Opt<")
        self.assertNotContains(response, ">Time<")
        self.assertNotContains(response, "Ignition Companion")
        self.assertNotContains(response, "Flux service console")
        self.assertContains(response, 'id="bridges-comp-card"')
        self.assertContains(response, 'data-comp-card-mode="summary"')
        self.assertContains(response, 'hx-select="#dashboard-comp-surface"')
        self.assertContains(response, "[↖]")
        self.assertNotContains(response, reverse("dashboard:bridges"))
        self.assertContains(response, "data-bridge-copy")
        self.assertContains(response, "data-bridge-copy-table")
        self.assertContains(response, "data-bridge-copy-llm")
        self.assertContains(response, "http://localhost:8001/apps/dashboard/#ignition-bridges")
        self.assertNotContains(response, "/admin/dashboard/ignitionbridgeconfig/")
        self.assertNotContains(response, "secret-token")
        self.assertContains(response, 'class="feature-hero"')
        self.assertContains(response, 'class="feature-hero-title"')
        self.assertContains(response, 'id="flux-page-content"')
        self.assertContains(response, "data-flux-web-pulse")
        self.assertContains(response, 'hx-trigger="every 5s [fluxDisplayPulseCanRun()]"')
        self.assertContains(response, "Next display refresh")
        self.assertContains(response, "flux-web-pulse-track")
        self.assertContains(response, "flux-web-pulse-timer")
        self.assertContains(response, "data-flux-web-pulse-timer")
        self.assertNotContains(response, "Flux.web pulse")
        self.assertNotContains(response, "cached display only")

    def test_home_links_feature_card_titles(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(
            response,
            '<h2><a class="card-title-link" href="/mine/">Flux.mine</a></h2>',
            html=True,
        )
        self.assertContains(response, 'id="fluxmine-comp-card"')
        self.assertContains(
            response,
            '<h2><a class="card-title-link" href="/build/">Flux.build</a></h2>',
            html=True,
        )
        self.assertContains(response, 'id="fluxbuild-comp-card"')

        self.assertContains(
            response,
            '<h2><a class="card-title-link" href="/sim/">Flux.sim</a></h2>',
            html=True,
        )
        self.assertContains(
            response,
            '<h2><a class="card-title-link" href="/spot/">Flux.spot</a></h2>',
            html=True,
        )
        self.assertContains(
            response,
            '<h2><a class="card-title-link" href="/chart/">Flux.chart</a></h2>',
            html=True,
        )

    def test_mine_and_build_pages_load_with_feature_hero(self):
        mine = self.client.get(reverse("mine:index"))
        build = self.client.get(reverse("build:index"))

        self.assertContains(mine, "Flux.mine")
        self.assertContains(mine, "Platform")
        self.assertContains(mine, 'class="feature-hero"')
        self.assertContains(build, "Flux.build")
        self.assertContains(build, "Platform")
        self.assertContains(build, 'class="feature-hero"')

    def test_removed_utility_pages_are_not_public_routes(self):
        for path in ("/nav/", "/opt/", "/time/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_home_bridge_comp_card_modes_render_status_and_config_link(self):
        IgnitionBridgeConfig.objects.create(
            name="default",
            role=IgnitionBridgeConfig.Role.SIMULATOR,
            base_url="http://sim.example.test/system/webdev/flux",
            token="secret-token",
        )

        detail = self.client.get(reverse("dashboard:home"), {"card": "bridges", "mode": "detail"})
        configure = self.client.get(reverse("dashboard:home"), {"card": "bridges", "mode": "configure"})

        self.assertContains(detail, 'id="dashboard-comp-focus"')
        self.assertContains(detail, 'id="bridges-comp-focus"')
        self.assertContains(detail, 'data-comp-card-mode="detail"')
        self.assertContains(detail, "[↘]")
        self.assertContains(detail, "default / Simulator")
        self.assertContains(detail, "http://sim.example.test/system/webdev/flux")
        self.assertContains(detail, "Stored token saved")
        self.assertContains(detail, "comp-card-anchor")
        self.assertContains(configure, 'id="bridges-comp-focus"')
        self.assertContains(configure, 'data-comp-card-mode="configure"')
        self.assertContains(configure, "[⚙]")
        self.assertContains(configure, 'value="http://sim.example.test/system/webdev/flux"')
        self.assertContains(configure, 'autocomplete="off"')
        self.assertContains(configure, "Remove stored token")
        self.assertContains(configure, "Use only when rotating credentials")
        self.assertContains(configure, "Do not use the Ignition gateway admin URL")
        self.assertContains(configure, "Bridge configuration docs")
        self.assertContains(configure, "Save bridge")
        self.assertContains(configure, "Test")
        self.assertContains(configure, "Delete")
        self.assertNotContains(configure, "Open bridge configuration")

    def test_home_bridge_configure_saves_bridge_inline(self):
        response = self.client.post(
            reverse("dashboard:home") + "?card=bridges&mode=configure",
            {
                "action": "save_bridge",
                "name": "prod",
                "role": IgnitionBridgeConfig.Role.PRODUCTION,
                "base_url": "http://prod.example.test/system/webdev/flux",
                "token": "secret-token",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dashboard-comp-surface"')
        self.assertContains(response, 'data-comp-mode="configure"')
        self.assertContains(response, "prod / Production")
        self.assertContains(response, "Save bridge")
        self.assertNotContains(response, "secret-token")
        self.assertTrue(IgnitionBridgeConfig.objects.filter(name="prod").exists())

    def test_home_sim_config_comp_card_renders_runtime_connection_breakout(self):
        endpoint = FieldEndpoint.objects.create(name="local-sim", enabled=True)
        device = create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        create_tag_config(device=device, name="Pressure", data_type=Tag.DataType.FLOAT, materialized=True)

        summary = self.client.get(reverse("dashboard:home"))

        self.assertContains(summary, 'id="sim-config-comp-card"')
        self.assertContains(summary, 'data-comp-card-mode="summary"')
        self.assertContains(summary, "Flux.sim")
        self.assertContains(summary, "OPC Servers")
        self.assertContains(summary, "Tags")
        self.assertNotContains(summary, "Generate provider model")

        detail = self.client.get(reverse("dashboard:home"), {"card": "sim-config", "mode": "detail"})
        configure = self.client.get(reverse("dashboard:home"), {"card": "sim-config", "mode": "configure"})

        self.assertContains(detail, 'id="sim-config-comp-focus"')
        self.assertContains(detail, "Runtime Connection")
        self.assertContains(detail, "SimServer endpoints are the running OPC side of Flux.sim")
        self.assertContains(configure, "OPC server runtime")
        self.assertContains(configure, "Start")

    def test_bridges_url_redirects_to_dashboard_configure_focus(self):
        response = self.client.get(reverse("dashboard:bridges"))

        self.assertRedirects(response, "/?card=bridges&mode=configure", fetch_redirect_response=False)

    def test_bridge_copy_context_exports_table_and_redacted_llm_payload(self):
        config = IgnitionBridgeConfig.objects.create(
            name="prod",
            role=IgnitionBridgeConfig.Role.PRODUCTION,
            base_url="http://prod.example.test/system/webdev/flux",
            token="secret-token",
            last_test_ok=True,
            last_test_message="Connected to Ignition 8.3.",
            last_test_at=timezone.now(),
        )

        table = render_bridge_table_markdown([config])
        llm = render_bridge_llm_markdown([config], page_url="http://testserver/")

        self.assertIn("| prod | Production | http://prod.example.test/system/webdev/flux | connected, token set |", table)
        self.assertIn('"type":"flux.dashboard.ignition_bridges.context"', llm)
        self.assertIn('"token_set":true', llm)
        self.assertIn("http://localhost:8001/apps/dashboard/#ignition-bridges", llm)
        self.assertNotIn("secret-token", llm)

    def test_bridge_context_summarizes_fluxy_http_failures(self):
        config = IgnitionBridgeConfig.objects.create(
            name="sim",
            role=IgnitionBridgeConfig.Role.SIMULATOR,
            base_url="http://localhost:8088/system/webdev/flux",
            token="secret-token",
            last_test_ok=False,
            last_test_message='Fluxy bridge returned HTTP 402: {\n"message":"Trial Expired",\n"url":"/system/webdev/flux/fluxy/util/getVersion"\n}',
            last_test_at=timezone.now(),
        )

        table = render_bridge_table_markdown([config])
        llm = render_bridge_llm_markdown([config], page_url="http://testserver/")

        self.assertIn("HTTP 402: Trial Expired", table)
        self.assertIn('"message":"HTTP 402: Trial Expired"', llm)
        self.assertNotIn("/fluxy/util/getVersion", llm)

    def test_home_renders_flux_serve_heartbeat_card(self):
        ServeHeartbeat.objects.create(
            service_name="flux-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            current_job="reading runtime tags",
            last_seen_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard:home"), {"card": "serve", "mode": "detail"})

        self.assertContains(response, "Flux.serve")
        self.assertContains(response, "Heartbeat rows describe supervisor and worker health")
        self.assertContains(response, "1/1 services running")
        self.assertContains(response, "Serve Logs")

    def test_home_renders_flux_serve_heartbeat_pid_and_port_evidence(self):
        ServeHeartbeat.objects.create(
            service_name="flux-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            pid=1234,
            metadata={"port": 9901},
            last_seen_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard:home"), {"card": "serve", "mode": "detail"})

        self.assertContains(response, "PID 1234")
        self.assertContains(response, "port 9901")

    def test_home_renders_flux_serve_observed_health_when_snapshots_exist(self):
        ServeServiceSnapshot.objects.create(
            service_key="Flux.web.server",
            display_name="Flux Web Server",
            category="Web",
            desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary="HTTP 200",
            metadata={"pid": 4321, "port": 8000},
        )

        response = self.client.get(reverse("dashboard:home"), {"card": "serve", "mode": "detail"})

        self.assertContains(response, "Observed service health")
        self.assertContains(response, "Flux.web.server")
        self.assertContains(response, "PID 4321")
        self.assertContains(response, "port 8000")
        self.assertContains(response, "1/1 services healthy")

    def test_home_flux_serve_observed_health_uses_ten_row_htmx_pagination(self):
        for index in range(12):
            ServeServiceSnapshot.objects.create(
                service_key=f"Flux.test.service-{index:02d}",
                display_name=f"Service {index:02d}",
                category="Test",
                desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
                observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
                severity=ServeServiceSnapshot.Severity.OK,
                summary="HTTP 200",
            )

        first_page = self.client.get(reverse("dashboard:home"), {"card": "serve", "mode": "detail"})
        second_page = self.client.get(
            reverse("dashboard:home"),
            {"card": "serve", "mode": "detail", "dashboard_serve_page": "2"},
        )

        self.assertContains(first_page, "Showing 1-10 of 12 services")
        self.assertContains(first_page, 'hx-target="#dashboard-comp-surface"')
        self.assertContains(first_page, "dashboard_serve_page=2")
        self.assertContains(first_page, "Flux.test.service-09")
        self.assertNotContains(first_page, "Flux.test.service-10")
        self.assertContains(second_page, "Showing 11-12 of 12 services")
        self.assertContains(second_page, "dashboard_serve_page=1")
        self.assertContains(second_page, "Flux.test.service-10")
        self.assertNotContains(second_page, "Flux.test.service-09")

    def test_home_labels_field_endpoints_as_runtime_endpoints(self):
        FieldEndpoint.objects.all().delete()
        endpoint = FieldEndpoint.objects.create(
            name="local-sim",
            status=FieldEndpoint.Status.DISABLED,
            enabled=True,
        )
        device = create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        create_tag_config(device=device, name="Pressure", data_type=Tag.DataType.FLOAT, materialized=True)

        response = self.client.get(reverse("dashboard:home"), {"card": "sim-config", "mode": "configure"})

        self.assertContains(response, "Flux.sim")
        self.assertContains(response, "Runtime Connection")
        self.assertContains(response, "SimServer endpoints are the running OPC side of Flux.sim")
        self.assertContains(response, "1 configured device namespaces, 1 field tags")
        self.assertContains(response, "last reported disabled · no heartbeat")
        self.assertContains(response, "1 device namespaces · 1 tags")
        self.assertContains(response, "Start")
        self.assertContains(response, 'hx-target="#dashboard-comp-surface"')
        self.assertNotContains(response, "FieldAgent Devices")

    def test_start_sim_server_requests_flux_serve_command(self):
        endpoint = FieldEndpoint.objects.create(name="Flux sim OPC-UA Server", status=FieldEndpoint.Status.DISABLED)
        device = create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        create_tag_config(device=device, name="Pressure", data_type=Tag.DataType.FLOAT, materialized=True)

        started = start_sim_server(endpoint.id)

        started.refresh_from_db()
        command = ServeCommand.objects.get()
        self.assertEqual(started.status, FieldEndpoint.Status.STARTING)
        self.assertTrue(started.enabled)
        self.assertEqual(command.command, "start_sim_server")
        self.assertEqual(command.payload["endpoint_id"], endpoint.id)

    @patch("dashboard.views.start_sim_server")
    def test_home_start_button_posts_endpoint_start_action(self, start_sim_server_mock):
        endpoint = FieldEndpoint.objects.create(name="Flux sim OPC-UA Server", status=FieldEndpoint.Status.DISABLED)
        start_sim_server_mock.return_value = endpoint

        response = self.client.post(
            reverse("dashboard:home"),
            {"action": "start_sim_server", "endpoint_id": str(endpoint.id)},
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        start_sim_server_mock.assert_called_once_with(endpoint.id, requested_by=ANY)

    @patch("dashboard.views.start_sim_server")
    def test_home_start_button_htmx_returns_simserver_card(self, start_sim_server_mock):
        endpoint = FieldEndpoint.objects.create(name="Flux sim OPC-UA Server", status=FieldEndpoint.Status.DISABLED)
        start_sim_server_mock.return_value = endpoint

        response = self.client.post(
            reverse("dashboard:home"),
            {"action": "start_sim_server", "endpoint_id": str(endpoint.id)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dashboard-comp-surface"')
        self.assertNotContains(response, "Flux service console")
        start_sim_server_mock.assert_called_once_with(endpoint.id, requested_by=ANY)

    def test_home_start_button_htmx_returns_starting_card_that_polls_until_running(self):
        endpoint = FieldEndpoint.objects.create(name="Flux sim OPC-UA Server", status=FieldEndpoint.Status.DISABLED)

        response = self.client.post(
            reverse("dashboard:home") + "?card=sim-config&mode=configure",
            {"action": "start_sim_server", "endpoint_id": str(endpoint.id)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sim-config-comp-focus"')
        self.assertContains(response, "starting")
        self.assertContains(response, "Starting...")
        self.assertContains(response, 'hx-get="%s?card=sim-config&mode=configure"' % reverse("dashboard:home"))
        self.assertContains(response, 'hx-trigger="every 2s"')
        self.assertContains(response, 'hx-select="#dashboard-comp-surface"')

    def test_home_simserver_card_partial_get_returns_only_card(self):
        FieldEndpoint.objects.create(name="Flux sim OPC-UA Server", status=FieldEndpoint.Status.DISABLED)

        response = self.client.get(
            reverse("dashboard:home"),
            {"partial": "simserver_card"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="simserver-comp-card"')
        self.assertNotContains(response, "Flux service console")

    def test_stop_sim_server_requests_flux_serve_command(self):
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.RUNNING,
            enabled=True,
        )
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:1",
            process_id=12345,
        )

        stopped = stop_sim_server(endpoint.id)
        command = ServeCommand.objects.get()

        self.assertEqual(stopped.status, FieldEndpoint.Status.DISABLED)
        self.assertFalse(stopped.enabled)
        self.assertEqual(command.command, "stop_sim_server")
        self.assertEqual(command.payload["endpoint_id"], endpoint.id)

    @patch("dashboard.views.stop_sim_server")
    def test_home_stop_button_posts_endpoint_stop_action(self, stop_sim_server_mock):
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.RUNNING,
            enabled=True,
        )
        stop_sim_server_mock.return_value = endpoint

        response = self.client.post(
            reverse("dashboard:home"),
            {"action": "stop_sim_server", "endpoint_id": str(endpoint.id)},
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        stop_sim_server_mock.assert_called_once_with(endpoint.id, requested_by=ANY)

    @patch("dashboard.views.stop_sim_server")
    def test_home_stop_button_htmx_returns_simserver_card(self, stop_sim_server_mock):
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.RUNNING,
            enabled=True,
        )
        stop_sim_server_mock.return_value = endpoint

        response = self.client.post(
            reverse("dashboard:home"),
            {"action": "stop_sim_server", "endpoint_id": str(endpoint.id)},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dashboard-comp-surface"')
        self.assertNotContains(response, "Flux service console")
        stop_sim_server_mock.assert_called_once_with(endpoint.id, requested_by=ANY)

    def test_home_uses_flux_live_configure_for_stale_recovery(self):
        tag = RuntimeTag.objects.create(provider="default", path="Demo/Stale", display_name="Stale Pressure", schedule=TagSchedule.objects.create(name="slow", interval_seconds=30))

        response = self.client.get(reverse("dashboard:home"), {"card": "spot", "mode": "configure"})

        self.assertContains(response, 'id="spot-comp-focus"')
        self.assertContains(response, "Stale tag recovery")
        self.assertContains(response, "Refresh stale reads now")
        self.assertContains(response, "Save refresh intervals")
        self.assertContains(response, "Hot")
        self.assertContains(response, "Warm")
        self.assertContains(response, "Cold")
        self.assertContains(response, tag.display_name)
        self.assertContains(response, tag.full_path)
        self.assertNotContains(response, 'id="stale-recovery-comp-card"')

    def test_home_live_detail_isolates_legacy_missing_flux_field_rows(self):
        schedule = TagSchedule.objects.create(name="slow", interval_seconds=30)
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Legacy/Meter/Level",
            display_name="Level",
            asset_name="Legacy Meter",
            schedule=schedule,
        )
        read_at = timezone.now()
        LatestTagValue.objects.create(
            tag=tag,
            value=0,
            quality_code='Error_Configuration("Server \\"Flux Field\\" does not exist.")',
            value_timestamp=read_at,
            read_at=read_at,
        )

        response = self.client.get(reverse("dashboard:home"), {"card": "spot", "mode": "detail"})

        self.assertContains(response, "0 active")
        self.assertContains(response, "No active stale runtime tags need refresh")
        self.assertNotContains(response, "legacy Flux Field rows hidden")
        self.assertNotContains(response, "[default]Legacy/Meter/Level")
        self.assertNotContains(response, "Legacy Meter / Level")
        self.assertNotContains(response, "legacy source missing")
        self.assertNotContains(response, "Legacy cleanup candidate")

    def test_home_live_detail_keeps_active_stale_rows_separate_from_legacy_rows(self):
        schedule = TagSchedule.objects.create(name="slow", interval_seconds=30)
        RuntimeTag.objects.create(
            provider="default",
            path="Demo/Pump/Pressure",
            display_name="Pressure",
            asset_name="Demo Pump",
            schedule=schedule,
        )
        legacy_tag = RuntimeTag.objects.create(
            provider="default",
            path="FluxLiveDemo/DemoMeter_01_FLOW_RATE",
            display_name="Flow Rate",
            asset_name="Meter: DemoMeter_01",
            schedule=schedule,
        )
        read_at = timezone.now()
        LatestTagValue.objects.create(
            tag=legacy_tag,
            value=0,
            quality_code='Error_Configuration("Server \\"Flux Field\\" does not exist.")',
            value_timestamp=read_at,
            read_at=read_at,
        )

        response = self.client.get(reverse("dashboard:home"), {"card": "spot", "mode": "detail"})

        self.assertContains(response, "1 active")
        self.assertContains(response, "Demo Pump / Pressure")
        self.assertNotContains(response, "legacy Flux Field rows hidden")
        self.assertNotContains(response, "FluxLiveDemo/DemoMeter_01_FLOW_RATE")
        self.assertNotContains(response, "Meter: DemoMeter_01 / Flow Rate")
        self.assertNotContains(response, "legacy source missing")

    def test_home_live_stale_recovery_uses_ten_row_htmx_pagination(self):
        schedule = TagSchedule.objects.create(name="slow", interval_seconds=30)
        for index in range(12):
            RuntimeTag.objects.create(
                provider="default",
                path=f"Demo/Stale_{index:02d}",
                display_name=f"Stale Tag {index:02d}",
                asset_name="Demo Area",
                schedule=schedule,
            )

        first_page = self.client.get(reverse("dashboard:home"), {"card": "spot", "mode": "detail"})
        second_page = self.client.get(
            reverse("dashboard:home"),
            {"card": "spot", "mode": "detail", "live_stale_page": "2"},
        )

        self.assertContains(first_page, "Showing 1-10 of 12 stale tags")
        self.assertContains(first_page, 'hx-target="#dashboard-comp-surface"')
        self.assertContains(first_page, "live_stale_page=2")
        self.assertContains(first_page, "Stale Tag 09")
        self.assertNotContains(first_page, "Stale Tag 10")
        self.assertContains(second_page, "Showing 11-12 of 12 stale tags")
        self.assertContains(second_page, "live_stale_page=1")
        self.assertContains(second_page, "Stale Tag 10")
        self.assertNotContains(second_page, "Stale Tag 09")

    def test_home_live_configure_updates_refresh_lane_intervals(self):
        response = self.client.post(
            reverse("dashboard:home") + "?card=spot&mode=configure",
            {
                "action": "save_live_refresh_lanes",
                "hot_interval_seconds": "5",
                "warm_interval_seconds": "20",
                "cold_interval_seconds": "120",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="spot-comp-focus"')
        self.assertContains(response, "Saved Flux.spot refresh intervals.")
        self.assertEqual(RefreshLane.objects.get(name="hot").interval_seconds, 5)
        self.assertEqual(RefreshLane.objects.get(name="warm").interval_seconds, 20)
        self.assertEqual(RefreshLane.objects.get(name="cold").interval_seconds, 120)

    def test_home_live_configure_imports_live_scope_csv(self):
        csv_upload = SimpleUploadedFile(
            "live.csv",
            b"scope,card,kind,point,full_path\npad,Well 1,well,Pressure,[default]Demo/Pressure\n",
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("dashboard:home") + "?card=spot&mode=configure",
            {"action": "import_live_scope_csv", "live_scope_csv": csv_upload},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="spot-comp-focus"')
        self.assertContains(response, "Imported 1 spot scopes, 1 cards, and 1 points.")
        self.assertTrue(LiveScope.objects.filter(slug="pad").exists())

    def test_home_live_configure_defaults_blank_scope_to_fluxolot(self):
        csv_upload = SimpleUploadedFile(
            "live.csv",
            b"card,kind,point,full_path\nWell 1,well,Pressure,[default]Demo/Pressure\n",
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("dashboard:home") + "?card=spot&mode=configure",
            {"action": "import_live_scope_csv", "live_scope_csv": csv_upload},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imported 1 spot scopes, 1 cards, and 1 points.")
        self.assertTrue(LiveScope.objects.filter(slug="Fluxolot").exists())

    def test_home_renders_flux_trace_card_detail_and_csv_import(self):
        profile = TraceProfile.objects.create(key="custom-chart", label="Custom chart")

        summary = self.client.get(reverse("dashboard:home"))
        detail = self.client.get(reverse("dashboard:home"), {"card": "chart", "mode": "detail"})

        self.assertContains(summary, 'id="chart-comp-card"')
        self.assertContains(summary, "Flux.chart")
        self.assertContains(summary, "1 Charts")
        self.assertContains(detail, 'id="chart-comp-focus"')
        self.assertContains(detail, "Charts")
        self.assertContains(detail, reverse("chart:nav-well-trace"))
        self.assertContains(detail, reverse("chart:index"))
        self.assertContains(detail, "Dashboard detail intentionally avoids rendering every chart link")
        self.assertNotContains(detail, reverse("chart:scope-profile", args=[profile.key]))

    def test_home_trace_configure_imports_trace_scope_csv(self):
        csv_upload = SimpleUploadedFile(
            "trace.csv",
            b"Chart Scope,Name,Tag 1\nwells,Well traces,[default]Demo/Pressure\n",
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("dashboard:home") + "?card=chart&mode=configure",
            {"action": "import_trace_scope_csv", "trace_scope_csv": csv_upload},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chart-comp-focus"')
        self.assertContains(response, "What is this?")
        self.assertContains(response, "| Chart Scope | Name | Tag 1 | Tag 2 |")
        self.assertContains(response, "Imported 1 charts, 1 tags, and 1 signals.")
        self.assertTrue(TraceProfile.objects.filter(key="wells").exists())

    def test_home_hides_stale_recovery_standalone_card_when_no_stale_tags(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "Flux.spot")
        self.assertNotContains(response, 'id="stale-recovery-comp-card"')
        self.assertNotContains(response, "Latest Tag Snapshots")

    def test_save_bridge_blank_token_keeps_existing_token(self):
        config = IgnitionBridgeConfig.objects.create(name="default", base_url="http://old.test", token="secret-token")

        response = self.client.post(
            reverse("dashboard:home"),
            {"action": "save_bridge", "fluxy_base_url": "http://new.test/system/webdev/flux", "fluxy_token": ""},
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        config.refresh_from_db()
        self.assertEqual(config.base_url, "http://new.test/system/webdev/flux")
        self.assertEqual(config.token, "secret-token")

    def test_save_bridge_can_clear_token(self):
        config = IgnitionBridgeConfig.objects.create(name="default", base_url="http://old.test", token="secret-token")

        response = self.client.post(
            reverse("dashboard:home"),
            {
                "action": "save_bridge",
                "fluxy_base_url": "http://old.test",
                "fluxy_token": "",
                "clear_fluxy_token": "on",
            },
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        config.refresh_from_db()
        self.assertEqual(config.token, "")


class DashboardReadinessTests(TestCase):
    def setUp(self):
        self.schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)

    def create_tag(self, name="Pressure", *, read_age_seconds=None, quality="Good"):
        tag = RuntimeTag.objects.create(
            provider="default",
            path=f"Demo/{name}",
            display_name=name,
            schedule=self.schedule,
        )
        if read_age_seconds is not None:
            read_at = timezone.now() - timezone.timedelta(seconds=read_age_seconds)
            LatestTagValue.objects.create(
                tag=tag,
                value=1.0,
                quality_code=quality,
                value_timestamp=read_at,
                read_at=read_at,
            )
        return tag

    def test_runtime_state_marks_missing_read_as_stale(self):
        tags = [self.create_tag()]

        state = dashboard_runtime_state(tags)

        self.assertEqual(state["tag_count"], 1)
        self.assertEqual(state["online_count"], 0)
        self.assertEqual(state["stale_count"], 1)
        self.assertEqual(state["stale_tag_items"][0]["reason"], "No read recorded")

    def test_runtime_state_marks_old_read_as_stale(self):
        tags = [self.create_tag(read_age_seconds=300)]

        state = dashboard_runtime_state(tags)

        self.assertEqual(state["online_count"], 0)
        self.assertEqual(state["stale_count"], 1)
        self.assertIn("Last read older", state["stale_tag_items"][0]["reason"])

    def test_runtime_state_marks_recent_good_read_online(self):
        tags = [self.create_tag(read_age_seconds=10)]

        state = dashboard_runtime_state(tags)

        self.assertEqual(state["online_count"], 1)
        self.assertEqual(state["stale_count"], 0)
        self.assertEqual(state["bad_quality_count"], 0)

    def test_runtime_state_counts_bad_quality(self):
        tags = [self.create_tag(read_age_seconds=10, quality="Bad_NotConnected")]

        state = dashboard_runtime_state(tags)

        self.assertEqual(state["online_count"], 0)
        self.assertEqual(state["stale_count"], 1)
        self.assertEqual(state["bad_quality_count"], 1)
        self.assertEqual(state["stale_tag_items"][0]["reason"], "Bad quality: Bad_NotConnected")

    def test_runtime_state_counts_bad_notfound_as_error(self):
        tags = [self.create_tag(read_age_seconds=10, quality="Bad_NotFound")]

        state = dashboard_runtime_state(tags)
        readiness = dashboard_readiness(state)

        self.assertEqual(state["online_count"], 0)
        self.assertEqual(state["stale_count"], 1)
        self.assertEqual(state["bad_quality_count"], 1)
        self.assertEqual(state["stale_tag_items"][0]["reason"], "Bad quality: Bad_NotFound")
        latest = [item for item in readiness if item.label == "Flux.spot"][0]
        self.assertEqual(latest.state, "error")
        self.assertEqual(latest.detail, "0 online, 1 stale, 1 bad")

    def test_interface_runtime_tags_excludes_trace_stress_tags(self):
        self.create_tag("Live", read_age_seconds=10)
        RuntimeTag.objects.create(
            provider="default",
            path="FluxTraceNavWells/1/PressureA",
            display_name="Pressure A",
            category=RuntimeTag.Category.TRACE_STRESS,
            schedule=self.schedule,
        )
        RuntimeTag.objects.create(
            provider="default",
            path="FluxTraceOilfieldLive1/PressureA",
            display_name="Oilfield Pressure A",
            category=RuntimeTag.Category.TRACE_STRESS,
            schedule=self.schedule,
        )

        tags = list(interface_runtime_tags())

        self.assertEqual([tag.path for tag in tags], ["Demo/Live"])
        self.assertEqual(excluded_interface_runtime_tag_count(), 2)

    def test_field_device_status_summarizes_endpoints_devices_and_tags(self):
        FieldEndpoint.objects.all().delete()
        endpoint = FieldEndpoint.objects.create(
            name="FieldAgent",
            status=FieldEndpoint.Status.RUNNING,
            last_seen_at=timezone.now(),
        )
        FieldAgentHeartbeat.objects.create(endpoint=endpoint, instance_id="field-agent:1")
        device = create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        create_tag_config(device=device, name="Pressure", data_type=Tag.DataType.FLOAT, materialized=True)

        status = field_device_status()

        self.assertEqual(status["enabled_endpoint_count"], 1)
        self.assertEqual(status["running_endpoint_count"], 1)
        self.assertEqual(status["enabled_device_count"], 1)
        self.assertEqual(status["enabled_tag_count"], 1)
        self.assertEqual(status["endpoint_items"][0]["endpoint"], endpoint)

    def test_field_device_status_includes_latest_heartbeat_evidence(self):
        FieldEndpoint.objects.all().delete()
        endpoint = FieldEndpoint.objects.create(
            name="FieldAgent",
            status=FieldEndpoint.Status.RUNNING,
            endpoint_url="opc.tcp://localhost:5061/flux/field",
            last_seen_at=timezone.now(),
        )
        create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        heartbeat = FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:1",
            process_id=12345,
        )

        status = field_device_status()

        self.assertEqual(status["endpoint_items"][0]["latest_heartbeat"], heartbeat)
        self.assertEqual(status["endpoint_items"][0]["endpoint_port"], 5061)
        self.assertEqual(status["endpoint_items"][0]["observed_state"], "reported running · fresh heartbeat")

    def test_field_device_status_does_not_probe_or_refresh_live_fieldagent_heartbeat(self):
        FieldEndpoint.objects.all().delete()
        old_seen_at = timezone.now() - timezone.timedelta(seconds=300)
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.STARTING,
            last_seen_at=old_seen_at,
        )
        create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        heartbeat = FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:1",
            process_id=12345,
            last_seen_at=old_seen_at,
            last_error="old error",
        )

        status = field_device_status()
        endpoint.refresh_from_db()
        heartbeat.refresh_from_db()

        self.assertEqual(endpoint.status, FieldEndpoint.Status.STARTING)
        self.assertEqual(endpoint.last_seen_at, old_seen_at)
        self.assertEqual(heartbeat.last_seen_at, old_seen_at)
        self.assertEqual(heartbeat.last_error, "old error")
        self.assertEqual(status["running_endpoint_count"], 0)

    def test_field_device_status_does_not_restart_disabled_endpoint_from_live_heartbeat(self):
        FieldEndpoint.objects.all().delete()
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.DISABLED,
            enabled=False,
        )
        create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:1",
            process_id=12345,
        )

        status = field_device_status()
        endpoint.refresh_from_db()

        self.assertEqual(endpoint.status, FieldEndpoint.Status.DISABLED)
        self.assertFalse(endpoint.enabled)
        self.assertEqual(status["running_endpoint_count"], 0)

    def test_field_device_status_does_not_mark_dead_fieldagent_process_error(self):
        FieldEndpoint.objects.all().delete()
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.RUNNING,
        )
        create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        heartbeat = FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:1",
            process_id=12345,
        )

        status = field_device_status()
        endpoint.refresh_from_db()
        heartbeat.refresh_from_db()

        self.assertEqual(endpoint.status, FieldEndpoint.Status.RUNNING)
        self.assertEqual(endpoint.last_error, "")
        self.assertEqual(heartbeat.process_id, 12345)
        self.assertEqual(status["running_endpoint_count"], 1)

    def test_home_sim_config_shows_stored_runtime_pid_and_port_evidence(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")
        FieldEndpoint.objects.all().delete()
        endpoint = FieldEndpoint.objects.create(
            name="Flux sim OPC-UA Server",
            status=FieldEndpoint.Status.RUNNING,
            endpoint_url="opc.tcp://0.0.0.0:5061/flux/field",
        )
        create_device_config(endpoint=endpoint, name="DeviceA", device_type="Simulator")
        FieldAgentHeartbeat.objects.create(
            endpoint=endpoint,
            instance_id="field-agent:1",
            process_id=12345,
            last_seen_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard:home"), {"card": "sim-config", "mode": "configure"})

        self.assertContains(response, "reported running · fresh heartbeat")
        self.assertContains(response, "PID 12345")
        self.assertContains(response, "port 5061")

    def test_serve_status_summarizes_running_stale_and_error_heartbeats(self):
        now = timezone.now()
        ServeHeartbeat.objects.create(
            service_name="running",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=now,
        )
        ServeHeartbeat.objects.create(
            service_name="stale",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=now - timezone.timedelta(seconds=300),
        )
        ServeHeartbeat.objects.create(
            service_name="error",
            instance_id="default",
            status=ServeHeartbeat.Status.ERROR,
            last_seen_at=now,
        )

        status = serve_status()

        self.assertEqual(status["total_count"], 3)
        self.assertEqual(status["running_count"], 1)
        self.assertEqual(status["stale_count"], 1)
        self.assertEqual(status["error_count"], 1)
        self.assertEqual(status["state"], "error")

    def test_serve_status_prefers_observed_snapshots_when_available(self):
        ServeHeartbeat.objects.create(
            service_name="running",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now(),
        )
        ServeServiceSnapshot.objects.create(
            service_key="Flux.web.server",
            display_name="Flux Web Server",
            category="Web",
            desired_state=ServeServiceSnapshot.DesiredState.REQUIRED,
            observed_state=ServeServiceSnapshot.ObservedState.HEALTHY,
            severity=ServeServiceSnapshot.Severity.OK,
            summary="HTTP 200",
        )

        status = serve_status()

        self.assertEqual(status["source"], "snapshots")
        self.assertEqual(status["ok_count"], 1)
        self.assertEqual(status["total_count"], 1)

    def test_readiness_includes_flux_serve_state(self):
        state = dashboard_runtime_state([self.create_tag(read_age_seconds=10)])
        serve_state = {
            "state": "warning",
            "running_count": 1,
            "stale_count": 2,
            "error_count": 0,
        }

        readiness = dashboard_readiness(state, serve_state)

        latest = [item for item in readiness if item.label == "Flux.serve"][0]
        self.assertEqual(latest.state, "warning")
        self.assertEqual(latest.detail, "1 running, 2 stale, 0 error")
        self.assertEqual(latest.detail_lines, ("1 running", "2 stale", "0 error"))

    def test_home_overall_not_ready_when_flux_serve_stale(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")
        ServeHeartbeat.objects.create(
            service_name="stale-worker",
            instance_id="default",
            status=ServeHeartbeat.Status.RUNNING,
            last_seen_at=timezone.now() - timezone.timedelta(seconds=300),
        )
        self.create_tag(read_age_seconds=10)

        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "Attention needed")
        self.assertContains(response, "Flux.serve")
        self.assertContains(response, "0 running")
        self.assertContains(response, "1 stale")
        self.assertContains(response, "0 error")

    @patch("dashboard.services.port_is_open", return_value=True)
    def test_readiness_reports_latest_reads_ok_when_clean(self, _port):
        state = dashboard_runtime_state([self.create_tag(read_age_seconds=10)])

        readiness = dashboard_readiness(state)

        latest = [item for item in readiness if item.label == "Flux.spot"][0]
        self.assertEqual(latest.state, "ok")

    @patch("dashboard.services.port_is_open", return_value=True)
    def test_readiness_reports_latest_reads_warning_when_stale_exists(self, _port):
        state = dashboard_runtime_state([
            self.create_tag("Fresh", read_age_seconds=10),
            self.create_tag("Stale", read_age_seconds=300),
        ])

        readiness = dashboard_readiness(state)

        latest = [item for item in readiness if item.label == "Flux.spot"][0]
        self.assertEqual(latest.state, "warning")


class FluxDoctorStateCommandTests(TestCase):
    def setUp(self):
        self.schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Demo/Pressure",
            display_name="Pressure",
            schedule=self.schedule,
        )
        read_at = timezone.now()
        LatestTagValue.objects.create(
            tag=tag,
            value=1.0,
            quality_code="Good",
            value_timestamp=read_at,
            read_at=read_at,
        )
        IgnitionBridgeConfig.objects.create(
            name="default",
            base_url="http://ignition.test/system/webdev/flux",
            token="secret-token",
        )

    @patch("dashboard.management.commands.flux_doctor_state.datasource_info")
    @patch("dashboard.management.commands.flux_doctor_state.fluxy_client")
    def test_flux_doctor_state_emits_runtime_bridge_and_historian_json(self, fluxy_client, datasource_info):
        class Version:
            version = "8.3.test"

        class Util:
            def get_version(self, refresh=False):
                return Version()

        class Datasource:
            name = "FluxyPostgres"
            db_type = "POSTGRES"
            status = "Valid"

        fluxy_client.return_value.util = Util()
        datasource_info.return_value = Datasource()
        output = StringIO()

        call_command("flux_doctor_state", stdout=output)

        import json

        payload = json.loads(output.getvalue())
        self.assertTrue(payload["bridge"]["online"])
        self.assertTrue(payload["bridge"]["token_set"])
        self.assertEqual(payload["runtime"]["tag_count"], 1)
        self.assertEqual(payload["runtime"]["stale_count"], 0)
        self.assertEqual(payload["runtime"]["excluded_interface_tag_count"], 0)
        self.assertEqual(payload["historian"]["db_type"], "POSTGRES")
