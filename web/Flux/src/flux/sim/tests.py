import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from flux.base.models import FieldDevice, FieldEndpoint, FieldTag, SimDevice, SimDeviceTag, SimDriver, SimServer, TagNode, TagProvider

from .provider_tree import build_imported_provider_tree, selected_source_paths
from .models import SimProviderSelection


class SimModelTests(TestCase):
    def test_sim_index_loads(self):
        response = self.client.get("/sim/")

        self.assertEqual(response.status_code, 200)

    def test_sim_index_has_no_legacy_memory_sim_workflow(self):
        response = self.client.get("/sim/")

        self.assertNotContains(response, "Legacy memory sim")
        self.assertNotContains(response, "scheduled tags")
        self.assertNotContains(response, "Backfills")
        self.assertNotContains(response, "Enable Folder")

    def test_sim_index_renders_catalog_and_runtime_counts(self):
        sim_server, _created = SimServer.objects.get_or_create(name="Flux sim OPC-UA Server")
        provider = TagProvider.objects.create(
            name="Tag_02",
            source="json_upload",
            source_sha256="abc",
            total_nodes=2,
            atomic_tag_count=2,
            sim_server=sim_server,
        )
        TagNode.objects.create(provider=provider, path="Area/RTU_01/PV", name="PV", tag_type="AtomicTag", value_source="opc")
        TagNode.objects.create(provider=provider, path="Area/RTU_01/SP", name="SP", tag_type="AtomicTag", value_source="opc")
        driver = SimDriver.objects.create(key="opc_ua", label="OPC UA", strategy_key="acm")
        sim_device = SimDevice.objects.create(provider=provider, name="RTU_01", driver=driver, enabled=True)
        SimDeviceTag.objects.create(
            provider=provider,
            device=sim_device,
            source_path="Area/RTU_01/PV",
            tag_name="PV",
            data_type="Float4",
            value_source="opc",
            enabled=True,
        )
        endpoint = FieldEndpoint.objects.create(name="sim-tag_02-rtu_01", enabled=True)
        field_device = FieldDevice.objects.create(
            endpoint=endpoint,
            name="RTU_01",
            device_type="OPC UA",
            description="Materialized from SimDevice catalog %s" % sim_device.id,
        )
        FieldTag.objects.create(device=field_device, name="PV", data_type=FieldTag.DataType.FLOAT, enabled=True)

        response = self.client.get("/sim/")

        self.assertContains(response, "Catalog and Runtime")
        self.assertContains(response, "1 Tag providers")
        self.assertContains(response, "1 devices, 2 OPC tags")
        self.assertContains(response, "1 Sim Servers")
        self.assertContains(response, "Currently simulating 1 device namespaces and 1 field tags")
        self.assertContains(response, "Control devices")

    def test_sim_index_does_not_build_imported_tree_without_selected_provider(self):
        TagProvider.objects.create(name="HugeProvider", source="json_upload", source_sha256="abc")

        with patch("flux.sim.views.build_imported_provider_tree") as build_tree:
            response = self.client.get("/sim/")

        self.assertEqual(response.status_code, 200)
        build_tree.assert_not_called()
        self.assertContains(response, "Choose a provider to browse imported branches")

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

    def test_sim_page_json_import_populates_base_provider(self):
        upload = SimpleUploadedFile(
            "simtag.json",
            json.dumps(provider_export_fixture()).encode("utf-8"),
            content_type="application/json",
        )

        response = self.client.post("/sim/import/json/", {"provider": "simtag", "provider_json": upload})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(TagProvider.objects.filter(name="simtag", source=TagProvider.Source.JSON_UPLOAD).exists())
        self.assertTrue(TagNode.objects.filter(provider__name="simtag", path="Area/Device01/PV").exists())

    def test_sim_page_ignition_import_uses_fluxy_export(self):
        fake_fx = SimpleNamespace(
            tag=SimpleNamespace(
                export_tags=lambda tag_path, recursive=True: SimpleNamespace(
                    tags=provider_export_fixture(),
                    raw_json=json.dumps(provider_export_fixture()),
                )
            )
        )
        with patch("flux.sim.views.fluxy.Fluxy", return_value=fake_fx) as fluxy_class:
            response = self.client.post(
                "/sim/import/ignition/",
                {"source_provider": "simtag", "provider": "simtag"},
            )

        self.assertEqual(response.status_code, 302)
        fluxy_class.assert_called_once()
        self.assertTrue(TagProvider.objects.filter(name="simtag", source=TagProvider.Source.IGNITION_PROVIDER).exists())
        self.assertTrue(TagNode.objects.filter(provider__name="simtag", path="Area/Device01/PV").exists())

    def test_sim_page_remove_ignition_tags_uses_fluxy_delete(self):
        fake_fx = FakeFluxy()
        with patch("flux.sim.views.fluxy.Fluxy", return_value=fake_fx):
            response = self.client.post(
                "/sim/remove-ignition-tags/",
                {"provider": "testsim", "folder_path": "FluxSim"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(fake_fx.tag.deleted, [["[testsim]FluxSim"]])


class FakeFluxy:
    def __init__(self):
        self.tag = FakeTagApi()


class FakeTagApi:
    def __init__(self):
        self.deleted = []

    def delete_tags(self, tag_paths):
        self.deleted.append(tag_paths)
        return ["Good" for _path in tag_paths]


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
