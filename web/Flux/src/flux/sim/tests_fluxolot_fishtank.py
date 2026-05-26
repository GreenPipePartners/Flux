import csv
import json
import sys
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from flux.sim.models import FieldEndpoint
from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample
from flux.plane.models import Sample
from flux.spot.models import LiveScope
from flux.sim.fluxolot_fishtank import (
    FLUXOLOT_LIVE_SCOPE,
    FLUXOLOT_TAG_FOLDER,
    FLUXOLOT_TAGS,
    FLUXOLOT_TANKS,
    configure_fluxolot_fishtank_ignition,
    ensure_fluxolot_fishtank,
    write_fluxolot_live_csv,
    write_fluxolot_live_scope_csv,
    write_fluxolot_trace_csv,
    write_fluxolot_trace_scope_csv,
)
from flux.sim.models import DeviceConfig, TagConfig
from flux.trace.models import TraceProfile


FLUXOLOT_PROVIDER_EXPORT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fluxolot_provider_export.json"


class FluxolotFishtankTests(TestCase):
    def test_fluxolot_provider_export_fixture_matches_fishtank_model(self):
        payload = json.loads(FLUXOLOT_PROVIDER_EXPORT_FIXTURE.read_text(encoding="utf-8"))
        atomic_tags = list(iter_atomic_tags(payload))

        self.assertEqual(payload["tagType"], "Provider")
        self.assertEqual(len(atomic_tags), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        self.assertEqual({tag["opcServer"] for _path, tag in atomic_tags}, {"FluxolotOPC"})
        expected_item_paths = {
            f"ns=2;s={tank.device_name}.{spec.name}"
            for tank in FLUXOLOT_TANKS
            for spec in FLUXOLOT_TAGS
        }
        self.assertEqual({tag["opcItemPath"] for _path, tag in atomic_tags}, expected_item_paths)

    def test_ensure_fluxolot_fishtank_creates_persistent_fixture(self):
        result = ensure_fluxolot_fishtank(history_days=2, history_interval_minutes=720)

        self.assertEqual([endpoint.name for endpoint in result.endpoints], [tank.endpoint_name for tank in FLUXOLOT_TANKS])
        self.assertEqual([device.name for device in result.devices], [tank.device_name for tank in FLUXOLOT_TANKS])
        self.assertEqual(len(result.field_tags), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        self.assertEqual(len(result.runtime_tags), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        endpoint_names = [tank.endpoint_name for tank in FLUXOLOT_TANKS]
        self.assertEqual(FieldEndpoint.objects.filter(name__in=endpoint_names).count(), 2)
        self.assertEqual(DeviceConfig.objects.filter(endpoint__name__in=endpoint_names).count(), 2)
        self.assertEqual(TagConfig.objects.filter(sim_device__endpoint__name__in=endpoint_names).count(), 26)
        self.assertEqual(RuntimeTag.objects.filter(path__startswith="FluxolotFishtank/").count(), 26)
        self.assertEqual(LatestTagValue.objects.count(), 26)
        self.assertEqual(TagSample.objects.count(), result.sample_count)
        self.assertTrue(RuntimeTag.objects.filter(asset_name="Sir Fluxolot Fishtank").exists())
        self.assertTrue(RuntimeTag.objects.filter(asset_name="Missus Fluxolot Fishtank").exists())

    def test_ensure_fluxolot_fishtank_is_idempotent(self):
        first = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=720)
        second = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=720)

        endpoint_names = [tank.endpoint_name for tank in FLUXOLOT_TANKS]
        self.assertEqual(FieldEndpoint.objects.filter(name__in=endpoint_names).count(), 2)
        self.assertEqual(DeviceConfig.objects.filter(endpoint__name__in=endpoint_names).count(), 2)
        self.assertEqual(TagConfig.objects.filter(sim_device__endpoint__name__in=endpoint_names).count(), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        self.assertEqual(RuntimeTag.objects.filter(path__startswith="FluxolotFishtank/").count(), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        self.assertEqual(TagSample.objects.count(), second.sample_count)
        self.assertEqual(first.sample_count, second.sample_count)

    def test_install_fluxolot_fishtank_command(self):
        call_command("install_fluxolot_fishtank", "--history-days", "1", "--history-interval-minutes", "1440")

        self.assertEqual(FieldEndpoint.objects.filter(name__in=[tank.endpoint_name for tank in FLUXOLOT_TANKS]).count(), 2)
        self.assertTrue(RuntimeTag.objects.filter(path__startswith="FluxolotFishtank/").exists())
        self.assertTrue(LiveScope.objects.filter(slug="fluxolot").exists())
        self.assertTrue(TraceProfile.objects.filter(key="fluxolot-sir").exists())
        self.assertTrue(TraceProfile.objects.filter(key="fluxolot-missus").exists())
        self.assertTrue(Sample.objects.filter(series__chart_signals__profile__key="fluxolot-sir").exists())
        self.assertTrue(Sample.objects.filter(series__chart_signals__profile__key="fluxolot-missus").exists())

    def test_install_fluxolot_fishtank_can_seed_year_long_trace_proof_dataset(self):
        call_command(
            "install_fluxolot_fishtank",
            "--history-years",
            "1",
            "--history-interval-minutes",
            "1440",
            "--plane-samples-all",
        )

        oldest = TagSample.objects.filter(tag__path__startswith="FluxolotFishtank/").order_by("read_at").first()
        newest = TagSample.objects.filter(tag__path__startswith="FluxolotFishtank/").order_by("-read_at").first()
        self.assertIsNotNone(oldest)
        self.assertIsNotNone(newest)
        self.assertGreaterEqual((newest.read_at.date() - oldest.read_at.date()).days, 365)
        self.assertEqual(TraceProfile.objects.get(key="fluxolot-sir").cache_window_minutes, 365 * 1440)
        self.assertGreaterEqual(Sample.objects.filter(series__chart_signals__profile__key="fluxolot-sir").count(), 8 * 365)
        self.assertGreaterEqual(Sample.objects.filter(series__chart_signals__profile__key="fluxolot-missus").count(), 8 * 365)

    def test_configure_fluxolot_fishtank_ignition_uses_fluxy_standard_apis(self):
        fx = FakeFluxy()

        result = configure_fluxolot_fishtank_ignition(fx, tag_provider="testing")

        self.assertEqual(result.connection_names, ["Flux Field sir-fluxolot-fishtank", "Flux Field missus-fluxolot-fishtank"])
        self.assertEqual(result.tag_base_path, "[testing]")
        self.assertEqual(result.tag_folder, FLUXOLOT_TAG_FOLDER)
        self.assertEqual(result.tag_count, len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        self.assertEqual(fx.tag.deleted, ["[testing]FluxolotFishtank"])
        self.assertEqual(fx.opcua.removed, ["Flux Field sir-fluxolot-fishtank", "Flux Field missus-fluxolot-fishtank"])
        self.assertEqual(len(fx.opcua.added), 2)
        endpoint_urls = {connection["endpoint_url"] for connection in fx.opcua.added}
        self.assertEqual(endpoint_urls, {tank.endpoint_url for tank in FLUXOLOT_TANKS})
        configured_tags = fx.tag.configured[0]["tags"][0]["tags"]
        self.assertEqual(len(configured_tags), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
        self.assertTrue(any(tag["name"].startswith("Sir-Fluxolot-Fishtank_") for tag in configured_tags))
        self.assertTrue(any(tag["name"].startswith("Missus-Fluxolot-Fishtank_") for tag in configured_tags))

    def test_writes_live_and_trace_csv_fixtures_from_runtime_tags(self):
        ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        with tempfile.TemporaryDirectory() as tmp_dir:
            live_path = Path(tmp_dir) / "fluxolot_live.csv"
            trace_path = Path(tmp_dir) / "fluxolot_trace.csv"

            live_rows = write_fluxolot_live_csv(live_path)
            trace_rows = write_fluxolot_trace_csv(trace_path)

            self.assertEqual(live_rows, len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))
            self.assertEqual(trace_rows, TagSample.objects.count())
            with live_path.open(newline="", encoding="utf-8") as csv_file:
                live = list(csv.DictReader(csv_file))
            with trace_path.open(newline="", encoding="utf-8") as csv_file:
                trace = list(csv.DictReader(csv_file))
            self.assertEqual(live[0]["scope"], FLUXOLOT_LIVE_SCOPE)
            self.assertTrue(live[0]["full_path"].startswith("[default]FluxolotFishtank/"))
            self.assertTrue(trace[0]["full_path"].startswith("[default]FluxolotFishtank/"))
            self.assertIn("value_timestamp", trace[0])

    def test_writes_scope_csv_fixtures_for_live_and_trace_importers(self):
        result = ensure_fluxolot_fishtank(history_days=1, history_interval_minutes=1440)
        with tempfile.TemporaryDirectory() as tmp_dir:
            live_path = write_fluxolot_live_scope_csv(Path(tmp_dir) / "live_scope.csv", result.runtime_tags)
            trace_path = write_fluxolot_trace_scope_csv(Path(tmp_dir) / "trace_scope.csv", result.runtime_tags)

            with live_path.open(newline="", encoding="utf-8") as csv_file:
                live = list(csv.DictReader(csv_file))
            with trace_path.open(newline="", encoding="utf-8") as csv_file:
                trace = list(csv.DictReader(csv_file))

        self.assertEqual(len(live), 8)
        self.assertEqual({row["Live Scope"] for row in live}, {"fluxolot"})
        self.assertIn("Sir Fluxolot Fish Tank", {row["Name"] for row in live})
        self.assertIn("Missus Fluxolot Fish Tank", {row["Name"] for row in live})
        self.assertEqual(trace[0]["Chart Scope"], "fluxolot")
        self.assertEqual(len(trace), 1)
        self.assertIn("Tag 1", trace[0])
        self.assertIn("Tag 16", trace[0])

    def test_install_command_can_configure_ignition_with_fake_fluxy(self):
        fake = FakeFluxy()
        fake_fluxy_module = SimpleNamespace(Fluxy=lambda **kwargs: fake)
        output = StringIO()

        with patch.dict(sys.modules, {"fluxy": fake_fluxy_module}):
            call_command(
                "install_fluxolot_fishtank",
                "--history-days",
                "1",
                "--history-interval-minutes",
                "1440",
                "--configure-ignition",
                "--tag-provider",
                "testing",
                stdout=output,
            )

        self.assertIn("Configured Fluxolot Fishtank Ignition", output.getvalue())
        self.assertEqual(len(fake.opcua.added), 2)
        self.assertEqual(len(fake.tag.configured[0]["tags"][0]["tags"]), len(FLUXOLOT_TAGS) * len(FLUXOLOT_TANKS))


class FakeFluxy:
    def __init__(self):
        self.opcua = FakeOpcUaNamespace()
        self.tag = FakeTagNamespace()


class FakeOpcUaNamespace:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_connection(
        self,
        name,
        description,
        discovery_url,
        endpoint_url,
        security_policy="None",
        security_mode="None",
        settings=None,
    ):
        self.added.append(
            {
                "name": name,
                "description": description,
                "discovery_url": discovery_url,
                "endpoint_url": endpoint_url,
                "security_policy": security_policy,
                "security_mode": security_mode,
                "settings": settings,
            }
        )
        return True

    def remove_connection(self, name):
        self.removed.append(name)
        return True


class FakeTagNamespace:
    def __init__(self):
        self.configured = []
        self.deleted = []

    def configure(self, tags, base_path=None, collision_policy="o"):
        self.configured.append({"tags": tags, "base_path": base_path, "collision_policy": collision_policy})
        return []

    def delete_tags(self, tag_paths):
        self.deleted.append(tag_paths)
        return []


def iter_atomic_tags(node, path=""):
    name = node.get("name") or ""
    node_path = f"{path}/{name}" if path and name else name or path
    if node.get("tagType") == "AtomicTag":
        yield node_path, node
    for child in node.get("tags") or []:
        yield from iter_atomic_tags(child, node_path)
