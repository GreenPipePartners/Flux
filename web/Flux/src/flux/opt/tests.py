from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample, TagSchedule
from flux.serve.models import ServeHeartbeat
from flux.serve.status import runtime_read_status
from flux.sim.fluxolot_fishtank import ensure_fluxolot_fishtank

from .models import OptimizationLease, RefreshLane
from .services import (
    HISTORY_CONFIGURATION_FIELDS,
    due_runtime_tags,
    history_metadata_report,
    lease_runtime_tags_hot,
    normalize_refresh_lanes,
    sample_due_runtime_tags,
    sample_runtime_demand,
    sample_runtime_tag_paths,
    runtime_tags_for_prefix,
)


class OptSmokeTests(TestCase):
    def test_opt_index_is_not_public_route(self):
        response = self.client.get("/opt/")

        self.assertEqual(response.status_code, 404)

    def test_run_optimizer_command_is_available(self):
        call_command("run_optimizer")


class SamplingServiceTests(TestCase):
    def setUp(self):
        self.schedule = TagSchedule.objects.create(name="fast", interval_seconds=10)

    def create_tag(self, path: str, *, enabled: bool = True, category: str = RuntimeTag.Category.PRODUCTION) -> RuntimeTag:
        return RuntimeTag.objects.create(
            provider="default",
            path=path,
            display_name=path.rsplit("/", 1)[-1],
            schedule=self.schedule,
            enabled=enabled,
            category=category,
        )

    def fluxy_client(self):
        class Value:
            def __init__(self, value):
                self.value = value
                self.quality = "Good"
                self.timestamp = timezone.now().isoformat()

        class TagClient:
            def __init__(self):
                self.paths = []
                self.config_paths = []

            def read_blocking(self, paths):
                self.paths.append(paths)
                return [Value(index) for index, _path in enumerate(paths, start=1)]

            def get_configuration(self, paths, recursive=False):
                self.config_paths.append((paths, recursive))
                normalized_paths = paths if isinstance(paths, list) else [paths]
                return [
                    {
                        "fullPath": path,
                        "name": path.rsplit("/", 1)[-1],
                        "historyEnabled": True,
                        "historyProvider": "default",
                        "historySampleMode": "OnChange",
                        "historySampleRate": 1,
                        "historySampleRateUnits": "SEC",
                        "ignoredNonHistoryField": "skip me",
                    }
                    for path in normalized_paths
                ]

        class FluxyClient:
            def __init__(self):
                self.tag = TagClient()

        return FluxyClient()

    def test_normalize_refresh_lanes_ensures_hot_warm_cold_without_deleting_existing_lanes(self):
        self.assertTrue(RefreshLane.objects.filter(name="cool").exists())

        normalize_refresh_lanes()

        self.assertTrue(RefreshLane.objects.filter(name="hot").exists())
        self.assertTrue(RefreshLane.objects.filter(name="warm").exists())
        self.assertTrue(RefreshLane.objects.filter(name="cold").exists())
        self.assertTrue(RefreshLane.objects.filter(name="cool").exists())

    def test_due_runtime_tags_returns_enabled_tags_without_current_reads(self):
        due = self.create_tag("Devices/Due")
        self.create_tag("Devices/Disabled", enabled=False)

        self.assertEqual(due_runtime_tags(), [due])

    def test_due_runtime_tags_respects_schedule_interval(self):
        now = timezone.now()
        fresh = self.create_tag("Devices/Fresh")
        stale = self.create_tag("Devices/Stale")
        LatestTagValue.objects.create(
            tag=fresh,
            value=1,
            value_timestamp=now,
            read_at=now - timezone.timedelta(seconds=5),
        )
        LatestTagValue.objects.create(
            tag=stale,
            value=2,
            value_timestamp=now,
            read_at=now - timezone.timedelta(seconds=10),
        )

        self.assertEqual(due_runtime_tags(now=now), [stale])

    def test_sample_due_runtime_tags_batches_reads_and_updates_latest_and_samples(self):
        first = self.create_tag("Devices/First")
        second = self.create_tag("Devices/Second")
        self.create_tag("Devices/Disabled", enabled=False)
        fx = self.fluxy_client()

        sampled = sample_due_runtime_tags(fx=fx, limit=2)

        self.assertEqual(sampled, 2)
        self.assertEqual(fx.tag.paths, [[first.full_path, second.full_path]])
        self.assertEqual(LatestTagValue.objects.count(), 2)
        self.assertEqual(TagSample.objects.count(), 2)

    def test_runtime_tags_for_prefix_returns_matching_enabled_tags(self):
        first = self.create_tag("FluxolotFishtank/Sir_TEMP", category=RuntimeTag.Category.SIMULATION)
        second = self.create_tag("FluxolotFishtank/Missus_TEMP", category=RuntimeTag.Category.SIMULATION)
        self.create_tag("FluxolotFishtank/Disabled", enabled=False, category=RuntimeTag.Category.SIMULATION)
        self.create_tag("Other/Tag", category=RuntimeTag.Category.SIMULATION)
        self.create_tag("FluxolotFishtank/Production")

        tags = runtime_tags_for_prefix(
            provider="default",
            path_prefix="FluxolotFishtank/",
            category=RuntimeTag.Category.SIMULATION,
        )

        self.assertEqual(tags, [second, first])

    def test_demand_lease_marks_fresh_runtime_tag_due_on_hot_interval(self):
        now = timezone.now()
        tag = self.create_tag("Devices/HotDemand")
        LatestTagValue.objects.create(
            tag=tag,
            value=1,
            value_timestamp=now,
            read_at=now - timezone.timedelta(seconds=2),
        )

        self.assertEqual(due_runtime_tags(now=now), [])

        leased = lease_runtime_tags_hot([tag], seconds=30, now=now)

        self.assertEqual(leased, 1)
        self.assertEqual(due_runtime_tags(now=now), [tag])

    def test_demand_lease_prioritizes_hot_runtime_tags_when_limited(self):
        now = timezone.now()
        stale = self.create_tag("Devices/StaleCold")
        hot = self.create_tag("Devices/LimitedHotDemand")
        for tag in (stale, hot):
            LatestTagValue.objects.create(
                tag=tag,
                value=1,
                value_timestamp=now,
                read_at=now - timezone.timedelta(seconds=10),
            )
        lease_runtime_tags_hot([hot], seconds=30, now=now)

        self.assertEqual(due_runtime_tags(now=now, limit=1), [hot])

    def test_expired_demand_lease_does_not_mark_runtime_tag_due(self):
        now = timezone.now()
        tag = self.create_tag("Devices/ExpiredDemand")
        LatestTagValue.objects.create(
            tag=tag,
            value=1,
            value_timestamp=now,
            read_at=now - timezone.timedelta(seconds=2),
        )
        OptimizationLease.objects.create(
            work_type="runtime_tag_demand",
            target_path=tag.full_path,
            claimed_by="test",
            claimed_at=now - timezone.timedelta(seconds=10),
            expires_at=now - timezone.timedelta(seconds=1),
        )

        self.assertEqual(due_runtime_tags(now=now), [])

    def test_sample_runtime_tag_paths_samples_explicit_full_paths_only(self):
        first = self.create_tag("Devices/ExplicitFirst")
        second = self.create_tag("Devices/ExplicitSecond")
        fx = self.fluxy_client()

        sampled = sample_runtime_tag_paths([second.full_path], fx=fx)

        self.assertEqual(sampled, 1)
        self.assertEqual(fx.tag.paths, [[second.full_path]])
        self.assertFalse(LatestTagValue.objects.filter(tag=first).exists())
        self.assertTrue(LatestTagValue.objects.filter(tag=second).exists())

    def test_sample_runtime_demand_leases_samples_and_reports_history_metadata(self):
        tag = self.create_tag("Devices/FullIntegration")
        fx = self.fluxy_client()

        report = sample_runtime_demand(full_paths=[tag.full_path], lease_seconds=15, fx=fx)

        self.assertEqual(report.sampled_count, 1)
        self.assertEqual(report.leased_count, 1)
        self.assertEqual(report.full_paths, (tag.full_path,))
        self.assertTrue(report.history.attempted)
        self.assertTrue(report.history.supported)
        self.assertEqual(report.history.full_path_count, 1)
        self.assertIsNone(report.history.error)
        self.assertEqual(report.history.tags[0]["fullPath"], tag.full_path)
        self.assertEqual(report.history.tags[0]["historyEnabled"], True)
        self.assertNotIn("ignoredNonHistoryField", report.history.tags[0])
        self.assertEqual(report.history.fields, HISTORY_CONFIGURATION_FIELDS)
        self.assertEqual(fx.tag.paths, [[tag.full_path]])
        self.assertEqual(fx.tag.config_paths, [([tag.full_path], False)])

    def test_history_metadata_report_falls_back_to_per_path_get_configuration(self):
        class TagClient:
            def __init__(self):
                self.calls = []

            def get_configuration(self, path, recursive=False):
                self.calls.append((path, recursive))
                if isinstance(path, list):
                    raise TypeError("batch unsupported")
                return [{"name": path.rsplit("/", 1)[-1], "historyEnabled": path.endswith("A") }]

        class FluxyClient:
            def __init__(self):
                self.tag = TagClient()

        fx = FluxyClient()

        report = history_metadata_report(["[default]Devices/A", "[default]Devices/B"], fx=fx)

        self.assertTrue(report.attempted)
        self.assertTrue(report.supported)
        self.assertIsNone(report.error)
        self.assertEqual(
            fx.tag.calls,
            [
                (["[default]Devices/A", "[default]Devices/B"], False),
                ("[default]Devices/A", False),
                ("[default]Devices/B", False),
            ],
        )
        self.assertEqual(report.tags[0]["fullPath"], "[default]Devices/A")
        self.assertEqual(report.tags[0]["historyEnabled"], True)
        self.assertEqual(report.tags[1]["fullPath"], "[default]Devices/B")
        self.assertEqual(report.tags[1]["historyEnabled"], False)

    def test_history_metadata_report_returns_error_when_get_configuration_fails(self):
        class TagClient:
            def get_configuration(self, _path, recursive=False):
                raise RuntimeError("gateway unavailable")

        class FluxyClient:
            tag = TagClient()

        report = history_metadata_report(["[default]Devices/A"], fx=FluxyClient())

        self.assertTrue(report.attempted)
        self.assertFalse(report.supported)
        self.assertEqual(report.full_path_count, 1)
        self.assertIn("gateway unavailable", report.error)
        self.assertEqual(report.tags, ())


class SamplingWorkerCommandTests(TestCase):
    def test_flux_sampling_worker_runs_one_heartbeat_with_mocked_fluxy(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        fake_fluxy = SimpleNamespace(Fluxy=lambda base_url, token: object())
        with patch.dict(sys.modules, {"fluxy": fake_fluxy}):
            with patch("flux.serve.management.commands.flux_sampling_worker.sample_due_runtime_tags", return_value=3):
                output = call_command("flux_sampling_worker", once=True)

        self.assertIsNone(output)

    def test_flux_sampling_worker_samples_fluxolot_profile_with_heartbeat(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        old_read_at = timezone.now() - timezone.timedelta(seconds=settings.STALE_AFTER_SECONDS + 60)
        LatestTagValue.objects.update(read_at=old_read_at, value_timestamp=old_read_at)

        class Value:
            def __init__(self, value):
                self.value = value
                self.quality = "Good"
                self.timestamp = timezone.now().isoformat()

        class TagClient:
            def __init__(self):
                self.paths = []

            def read_blocking(self, paths):
                self.paths.append(paths)
                return [Value(index) for index, _path in enumerate(paths, start=1)]

        class FluxyClient:
            def __init__(self):
                self.tag = TagClient()

        fx = FluxyClient()
        fake_fluxy = SimpleNamespace(Fluxy=lambda base_url, token: fx)

        with patch.dict(sys.modules, {"fluxy": fake_fluxy}):
            call_command("flux_sampling_worker", "--once", "--profile", "fluxolot-fishtank")

        heartbeat = ServeHeartbeat.objects.get(service_name="fluxolot-live-sampler")
        self.assertEqual(heartbeat.status, ServeHeartbeat.Status.RUNNING)
        self.assertEqual(len(fx.tag.paths), 1)
        self.assertEqual(len(fx.tag.paths[0]), 26)
        self.assertEqual(LatestTagValue.objects.count(), 26)
        self.assertTrue(
            all(
                runtime_read_status(value, now=timezone.now(), stale_after_seconds=settings.STALE_AFTER_SECONDS).online
                for value in LatestTagValue.objects.all()
            )
        )
        self.assertGreater(TagSample.objects.count(), 26)
