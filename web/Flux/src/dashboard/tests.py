from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from io import StringIO
from unittest.mock import patch

from .models import IgnitionBridgeConfig
from .services import dashboard_readiness, dashboard_runtime_state

from flux.base.runtime import LatestTagValue, RuntimeTag, TagSchedule


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

        self.assertRedirects(response, reverse("admin:index"))
        user = get_user_model().objects.get(username="admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_setup_redirects_when_user_already_exists(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")

        response = self.client.get(reverse("dashboard:setup"))

        self.assertRedirects(response, reverse("dashboard:home"))


class DashboardBridgeTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user(username="existing", password="test-pass")

    def test_home_renders_bridge_without_token_value(self):
        IgnitionBridgeConfig.objects.create(name="default", base_url="http://example.test/system/webdev/flux", token="secret-token")

        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "Live Ignition Bridge")
        self.assertContains(response, "token set")
        self.assertNotContains(response, "secret-token")

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

        self.assertEqual(state["online_count"], 1)
        self.assertEqual(state["bad_quality_count"], 1)

    @patch("dashboard.services.port_is_open", return_value=True)
    def test_readiness_reports_latest_reads_ok_when_clean(self, _port):
        state = dashboard_runtime_state([self.create_tag(read_age_seconds=10)])

        readiness = dashboard_readiness(state)

        latest = [item for item in readiness if item.label == "Latest reads"][0]
        self.assertEqual(latest.state, "ok")

    @patch("dashboard.services.port_is_open", return_value=True)
    def test_readiness_reports_latest_reads_warning_when_stale_exists(self, _port):
        state = dashboard_runtime_state([
            self.create_tag("Fresh", read_age_seconds=10),
            self.create_tag("Stale", read_age_seconds=300),
        ])

        readiness = dashboard_readiness(state)

        latest = [item for item in readiness if item.label == "Latest reads"][0]
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
        self.assertEqual(payload["historian"]["db_type"], "POSTGRES")
