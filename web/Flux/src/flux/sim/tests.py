from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .engine import configure_enabled_tags, run_history_backfill, value_for_tag, write_due_tags
from .models import SimHistoryBackfill, SimProviderSelection, SimSchedule, SimTag
from .provider_tree import build_imported_provider_tree, selected_source_paths


class SimModelTests(TestCase):
    def test_sim_index_loads(self):
        response = self.client.get("/sim/")

        self.assertEqual(response.status_code, 200)

    def test_sim_index_renders_provider_folder_tag_tree(self):
        SimTag.objects.update(enabled=False)
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        SimTag.objects.create(
            provider="ACM02",
            name="PV",
            folder_path="Area/Device01",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
        )

        response = self.client.get("/sim/")

        self.assertContains(response, "[ACM02]")
        self.assertContains(response, "Area/Device01")
        self.assertContains(response, "Enable Folder")

    def test_imported_provider_tree_uses_checkboxes_and_folder_icon(self):
        with TemporaryDirectory() as temp_dir:
            sim_dir = Path(temp_dir) / "sim"
            sim_dir.mkdir()
            source = Path(temp_dir) / "provider.json"
            database = sim_dir / "flux-sim.db"
            source.write_text(json.dumps(provider_export_fixture()), encoding="utf-8")
            call_command("import_tag_provider_export", str(source), "--database", str(database), "--provider", "ACM02")
            with self.settings(BASE_DIR=Path(temp_dir) / "a" / "b"):
                response = self.client.get("/sim/?provider=ACM02")

        self.assertContains(response, "data-sim-tree-checkbox")
        self.assertContains(response, "data-sim-tree-toggle")
        self.assertContains(response, "📁")
        self.assertContains(response, "&gt;")

    def test_provider_enable_action_updates_provider_tags_only(self):
        SimTag.objects.update(enabled=False)
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        acm_tag = SimTag.objects.create(
            provider="ACM02",
            name="PV",
            folder_path="Area/Device01",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
        )
        other_tag = SimTag.objects.create(
            provider="Other",
            name="PV",
            folder_path="Area/Device01",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
            enabled=False,
        )

        response = self.client.post(
            "/sim/set-enabled/",
            {"scope": "provider", "provider": "ACM02", "enabled": "1"},
        )
        acm_tag.refresh_from_db()
        other_tag.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(acm_tag.enabled)
        self.assertFalse(other_tag.enabled)

    def test_folder_disable_action_updates_descendant_tags(self):
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        parent_tag = SimTag.objects.create(
            provider="ACM02",
            name="PV",
            folder_path="Area",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
            enabled=True,
        )
        child_tag = SimTag.objects.create(
            provider="ACM02",
            name="SP",
            folder_path="Area/Device01",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
            enabled=True,
        )
        sibling_tag = SimTag.objects.create(
            provider="ACM02",
            name="PV",
            folder_path="Other",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
            enabled=True,
        )

        self.client.post(
            "/sim/set-enabled/",
            {"scope": "folder", "provider": "ACM02", "folder_path": "Area", "enabled": "0"},
        )
        parent_tag.refresh_from_db()
        child_tag.refresh_from_db()
        sibling_tag.refresh_from_db()

        self.assertFalse(parent_tag.enabled)
        self.assertFalse(child_tag.enabled)
        self.assertTrue(sibling_tag.enabled)

    def test_tag_enable_action_updates_single_tag(self):
        SimTag.objects.update(enabled=False)
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        tag = SimTag.objects.create(
            provider="ACM02",
            name="PV",
            folder_path="Area/Device01",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
            enabled=False,
        )

        self.client.post("/sim/set-enabled/", {"scope": "tag", "tag_id": tag.id, "enabled": "1"})
        tag.refresh_from_db()

        self.assertTrue(tag.enabled)

    def test_seeded_schedules_exist(self):
        self.assertTrue(SimSchedule.objects.filter(interval_seconds=1).exists())
        self.assertTrue(SimSchedule.objects.filter(interval_seconds=5).exists())
        self.assertTrue(SimSchedule.objects.filter(interval_seconds=10).exists())

    def test_value_generation_for_bool_integer_and_float(self):
        SimTag.objects.update(enabled=False)
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        bool_tag = SimTag.objects.create(
            name="BoolTag",
            folder_path="ValueTest",
            data_type=SimTag.DataType.BOOLEAN,
            pattern=SimTag.Pattern.BOOL_TOGGLE,
            period_samples=2,
            schedule=fast,
        )
        int_tag = SimTag.objects.create(
            name="IntegerTag",
            folder_path="ValueTest",
            data_type=SimTag.DataType.INT4,
            pattern=SimTag.Pattern.INT_RAMP,
            baseline=10,
            step=2,
            schedule=fast,
        )
        float_tag = SimTag.objects.create(
            name="FloatTag",
            folder_path="ValueTest",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            baseline=50,
            amplitude=10,
            period_samples=4,
            schedule=fast,
        )

        self.assertEqual([value_for_tag(bool_tag, index) for index in range(4)], [False, False, True, True])
        self.assertEqual(value_for_tag(int_tag, 3), 16)
        self.assertAlmostEqual(value_for_tag(float_tag, 1), 60.0)

    def test_write_due_tags_uses_schedules_and_advances_next_write(self):
        SimTag.objects.update(enabled=False)
        fx = FakeFluxy()
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        now = timezone.now()
        tag = SimTag.objects.create(
            name="IntegerTag",
            folder_path="WriteTest",
            data_type=SimTag.DataType.INT4,
            pattern=SimTag.Pattern.INT_RAMP,
            schedule=fast,
            next_write_at=now,
        )

        written = write_due_tags(fx, now=now)
        tag.refresh_from_db()

        self.assertEqual(written, 1)
        self.assertEqual(fx.tag.writes[0]["tag_paths"], ["[default]WriteTest/IntegerTag"])
        self.assertEqual(fx.tag.writes[0]["values"], [0])
        self.assertEqual(tag.sample_index, 1)
        self.assertEqual(tag.last_value, 0)
        self.assertEqual(tag.next_write_at, now + timedelta(seconds=1))

    def test_configure_enabled_tags_groups_by_folder(self):
        SimTag.objects.update(enabled=False)
        fx = FakeFluxy()
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        SimTag.objects.create(
            name="BoolTag",
            folder_path="ConfigTest",
            data_type=SimTag.DataType.BOOLEAN,
            pattern=SimTag.Pattern.BOOL_TOGGLE,
            schedule=fast,
        )

        configure_enabled_tags(fx)

        self.assertEqual(fx.tag.configured[0]["base_path"], "[default]")
        self.assertEqual(fx.tag.configured[0]["tags"][0]["name"], "ConfigTest")

    def test_history_backfill_writes_configured_tags(self):
        SimTag.objects.update(enabled=False)
        fx = FakeFluxy()
        fast = SimSchedule.objects.create(name="fast", interval_seconds=1)
        SimTag.objects.create(
            name="FloatTag",
            folder_path="HistoryTest",
            data_type=SimTag.DataType.FLOAT8,
            pattern=SimTag.Pattern.FLOAT_WAVE,
            schedule=fast,
        )
        backfill = SimHistoryBackfill.objects.create(
            name="one-day",
            history_prefix="histprov:Core Historian:/sys:gateway:/prov:default:/tag:FluxSim",
            start_at=timezone.now(),
            duration_days=1,
            interval_seconds=86_400,
        )

        written = run_history_backfill(fx, backfill)
        backfill.refresh_from_db()

        self.assertEqual(written, 2)
        self.assertEqual(backfill.status, SimHistoryBackfill.Status.COMPLETED)
        self.assertEqual(len(fx.historian.stored), 1)


class SimAdapterTests(TestCase):
    def test_import_command_loads_provider_export(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "provider.json"
            database = Path(temp_dir) / "sim.db"
            source.write_text(json.dumps(provider_export_fixture()), encoding="utf-8")

            call_command(
                "import_tag_provider_export",
                str(source),
                "--database",
                str(database),
                "--provider",
                "ACM02",
                "--batch-size",
                "2",
            )

            with sqlite3.connect(database) as connection:
                total_nodes = connection.execute(
                    "SELECT total_nodes FROM sim_provider WHERE name = ?",
                    ("ACM02",),
                ).fetchone()[0]

        self.assertEqual(total_nodes, 4)

    def test_imported_provider_tree_renders_and_selects_paths(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "provider.json"
            database = Path(temp_dir) / "sim.db"
            source.write_text(json.dumps(provider_export_fixture()), encoding="utf-8")
            call_command("import_tag_provider_export", str(source), "--database", str(database), "--provider", "ACM02")

            tree = build_imported_provider_tree("ACM02", database_path=database)
            SimProviderSelection.objects.create(provider="ACM02", path="Area")
            paths = selected_source_paths("ACM02", database_path=database)

            self.assertIsNotNone(tree)
            self.assertEqual(tree.nodes[0].name, "Area")
            self.assertEqual(tree.nodes[0].children_list[0].name, "Device01")
            self.assertEqual(tree.nodes[0].children_list[0].children_list, [])
            self.assertEqual(paths, ["Area/Device01/PV"])

    def test_imported_provider_tree_marks_partial_parent_selection(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "provider.json"
            database = Path(temp_dir) / "sim.db"
            source.write_text(json.dumps(provider_export_fixture()), encoding="utf-8")
            call_command("import_tag_provider_export", str(source), "--database", str(database), "--provider", "ACM02")
            SimProviderSelection.objects.create(provider="ACM02", path="Area/Device01")

            tree = build_imported_provider_tree("ACM02", database_path=database)

            self.assertIsNotNone(tree)
            self.assertFalse(tree.nodes[0].selected)
            self.assertTrue(tree.nodes[0].partial)
            self.assertTrue(tree.nodes[0].children_list[0].selected)

    def test_imported_provider_tree_keeps_standalone_atomic_tags_selectable(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "provider.json"
            database = Path(temp_dir) / "sim.db"
            source.write_text(json.dumps(standalone_atomic_provider_fixture()), encoding="utf-8")
            call_command("import_tag_provider_export", str(source), "--database", str(database), "--provider", "ACM02")

            tree = build_imported_provider_tree("ACM02", database_path=database)

            self.assertIsNotNone(tree)
            self.assertEqual(tree.nodes[0].children_list[0].name, "PV")
            self.assertEqual(tree.nodes[0].children_list[0].tag_type, "AtomicTag")

    def test_selected_paths_endpoint_exports_ui_selection_shape(self):
        SimProviderSelection.objects.create(provider="ACM02", path="Area")

        response = self.client.get("/sim/imported/selected-paths.json?provider=ACM02")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "ACM02")
        self.assertIn("selected_source_paths", response.json())

    def test_imported_bulk_selection_replaces_provider_paths(self):
        SimProviderSelection.objects.create(provider="ACM02", path="Old")
        SimProviderSelection.objects.create(provider="Other", path="Keep")

        response = self.client.post(
            "/sim/imported/set-bulk/",
            {"provider": "ACM02", "paths": ["Area", "Area/Device01"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(SimProviderSelection.objects.filter(provider="ACM02").values_list("path", flat=True)),
            ["Area", "Area/Device01"],
        )
        self.assertTrue(SimProviderSelection.objects.filter(provider="Other", path="Keep").exists())


class FakeFluxy:
    def __init__(self):
        self.tag = FakeTagApi()
        self.historian = FakeHistorianApi()


class FakeTagApi:
    def __init__(self):
        self.writes = []
        self.configured = []

    def write_blocking(self, tag_paths, values):
        self.writes.append({"tag_paths": tag_paths, "values": values})
        return ["Good" for _path in tag_paths]

    def configure(self, tags, *, base_path, collision_policy):
        self.configured.append({"tags": tags, "base_path": base_path, "collision_policy": collision_policy})
        return ["Good"]


class FakeHistorianApi:
    def __init__(self):
        self.stored = []

    def store_data_points(self, paths, values, *, timestamps, qualities):
        self.stored.append({"paths": paths, "values": values, "timestamps": timestamps, "qualities": qualities})
        return ["Good" for _path in paths]


def provider_export_fixture():
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device01",
                        "tagType": "UdtInstance",
                        "typeId": "[Tag_02]_types_/Device/SP/RTU",
                        "parameters": {
                            "OPC_Server": "ACM_02",
                            "OPC_Device": "Device01",
                        },
                        "tags": [
                            {
                                "name": "PV",
                                "tagType": "AtomicTag",
                                "valueSource": "opc",
                                "dataType": "Float4",
                                "opcServer": "ACM_02",
                                "opcItemPath": "ns=2;s=Device01.40001F",
                                "value": 12.5,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def standalone_atomic_provider_fixture():
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "PV",
                        "tagType": "AtomicTag",
                        "valueSource": "opc",
                        "dataType": "Float4",
                        "opcServer": "ACM_02",
                        "opcItemPath": "ns=2;s=Device01.40001F",
                    }
                ],
            }
        ],
    }
