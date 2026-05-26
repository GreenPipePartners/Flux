import json
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from flux.base.models import Tag
from flux.sim.models import FieldEndpoint
from flux.sim.models import SimDriver, SimServer, TagNode, TagProvider, TagSelection
from flux.base.services import data_type_icon, import_provider_json_bytes, provider_tree_children as base_provider_tree_children
from flux.sim.jobs import run_next_sim_job
from flux.sim.output import apply_selected_output, provider_default_modes, selected_output_plan
from flux.sim.rehydrate import apply_rehydration_plan, build_rehydration_plan, materialize_rehydration_backing

from .provider_tree import build_imported_provider_tree, replace_imported_selection, selected_source_paths
from .models import DeviceConfig, Provider, ProviderSelection, SimJob, TagConfig
from .testing import create_device_config, create_tag_config


FLUXOLOT_PROVIDER_EXPORT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fluxolot_provider_export.json"


def provider_row(name: str) -> Provider:
    provider, _created = Provider.objects.get_or_create(
        name=name,
        defaults={"source": Provider.Source.JSON_UPLOAD, "source_name": "test", "source_sha256": "test"},
    )
    return provider


class SimModelTests(TestCase):
    def test_sim_index_loads(self):
        response = self.client.get("/sim/")

        self.assertEqual(response.status_code, 200)

    def test_field_route_is_not_public_sim_runtime_surface(self):
        response = self.client.get("/field/")

        self.assertEqual(response.status_code, 404)

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
        sim_device = create_device_config(provider=provider, name="RTU_01", device_type="OPC UA", driver=driver, enabled=True)
        create_tag_config(
            device=sim_device,
            source_path="Area/RTU_01/PV",
            name="PV",
            data_type=Tag.DataType.FLOAT,
            value_source="opc",
            enabled=True,
            materialized=True,
        )
        endpoint = FieldEndpoint.objects.create(name="sim-tag_02-rtu_01", enabled=True)
        sim_device.endpoint = endpoint
        sim_device.save(update_fields=["endpoint", "updated_at"])

        summary = self.client.get("/sim/")
        detail = self.client.get("/sim/", {"card": "sim-catalog", "mode": "detail"})
        import_configure = self.client.get("/sim/", {"card": "sim-import", "mode": "configure"})
        output_summary = self.client.get("/sim/", {"card": "sim-output", "mode": "detail", "provider": "Tag_02"})

        self.assertContains(summary, "Flux.sim")
        self.assertContains(summary, "Platform")
        self.assertContains(summary, "feature-hero")
        self.assertContains(summary, 'id="sim-comp-surface"')
        self.assertContains(summary, 'data-comp-card-grid')
        self.assertContains(summary, "Flux.sim.catalog")
        self.assertContains(summary, "Flux.sim.runtime")
        self.assertContains(summary, "FieldAgent Runtime")
        self.assertContains(summary, "this card does not run probes itself")
        self.assertContains(summary, "1 Tag Providers")
        self.assertContains(summary, "1 Devices")
        self.assertContains(summary, "2 Tags")
        self.assertNotContains(summary, "Flux Sim Platform")
        self.assertNotContains(summary, "flux.sim.platform.context")
        self.assertContains(summary, "flux.sim.catalog.surface.context")
        self.assertContains(summary, "flux.sim.import.surface.context")
        self.assertContains(summary, "flux.sim.output.surface.context")
        self.assertContains(summary, "data-flux-link-copy")
        self.assertNotContains(summary, 'id="sim-platform-comp-card"')
        self.assertNotContains(summary, "Flux.sim.delete")

        self.assertContains(detail, 'id="sim-catalog-comp-focus"')
        self.assertContains(detail, "1 Tag Providers")
        self.assertContains(detail, "1 Devices")
        self.assertContains(detail, "2 Tags")
        self.assertNotContains(detail, "Tag provider list")
        self.assertNotContains(detail, "Device list")
        self.assertNotContains(detail, "OPC tag list")
        self.assertNotContains(detail, '<details class="stage-card" open>')
        self.assertContains(detail, "Tag_02")
        self.assertContains(detail, "RTU_01")
        self.assertContains(detail, "[Tag_02]Area/RTU_01/PV")
        self.assertNotContains(detail, "/admin/base/simdevice/")

        self.assertContains(import_configure, "Flux.sim.import")
        self.assertContains(import_configure, "Generate From JSON Import")
        self.assertContains(import_configure, "Import From Ignition")
        self.assertContains(import_configure, 'data-comp-card-mode="configure"')

        self.assertContains(output_summary, "Flux.sim.output")
        self.assertContains(output_summary, "Desired Simulator Output")
        self.assertNotContains(output_summary, 'id="sim-provider-tree-comp-card"')

    def test_sim_index_summary_does_not_render_configure_workflows(self):
        TagProvider.objects.create(name="HugeProvider", source="json_upload", source_sha256="abc")

        response = self.client.get("/sim/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flux.sim.catalog")
        self.assertContains(response, "Flux.sim.import")
        self.assertContains(response, "Flux.sim.output")
        self.assertNotContains(response, "Choose a provider to browse imported branches")
        self.assertNotContains(response, "Generate From JSON Import")
        self.assertNotContains(response, "Apply Selection to Simulator Output")

    def test_sim_output_detail_preserves_provider_tree_selection(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="ACM02")

        response = self.client.get("/sim/?card=sim-output&mode=detail&provider=ACM02")
        child_response = self.client.get("/sim/imported/tree/children/", {"provider": "ACM02", "parent": "Area"})
        tag_response = self.client.get("/sim/imported/tree/children/", {"provider": "ACM02", "parent": "Area/Device01"})

        self.assertContains(response, "Desired Simulator Output")
        self.assertContains(response, "data-sim-tree-checkbox")
        self.assertContains(response, "data-sim-tree-toggle")
        self.assertContains(response, "📁")
        self.assertContains(response, "typed defaults")
        self.assertContains(response, "default_mode_numeric")
        self.assertContains(response, "default_mode_boolean")
        self.assertContains(response, "default_mode_text")
        self.assertContains(response, "Folder checks select scope; mode overrides appear only on atomic tags")
        self.assertContains(response, "Start Simulation")
        self.assertContains(response, 'name="rehydrate" value="1"')
        self.assertNotContains(response, "Confirm selected imported tags should start simulator output")
        self.assertNotContains(response, "confirm_apply")
        self.assertContains(response, "x^2")
        self.assertContains(response, "?*")
        self.assertContains(response, "R[]")
        self.assertContains(response, "~^~")
        self.assertContains(response, "?01")
        self.assertContains(response, "==")
        self.assertContains(response, "Random Range")
        self.assertContains(response, "hx-get")
        self.assertContains(response, 'hx-target="#sim-tree-children-')
        self.assertContains(response, 'hx-target="#sim-comp-surface"')
        self.assertContains(response, 'hx-select="#sim-comp-surface"')
        self.assertContains(response, 'hx-push-url="true"')
        self.assertNotContains(response, 'onchange="this.form.submit()"')
        self.assertContains(response, '?card=sim-output&mode=configure&amp;provider=ACM02')
        self.assertNotContains(response, "provider branch selection(s)")
        self.assertNotContains(response, "Selected branches")
        self.assertNotContains(response, 'title="Area/Device01/PV"')
        self.assertContains(child_response, "Device01")
        self.assertContains(child_response, "◆")
        self.assertContains(child_response, 'hx-get="/sim/imported/tree/children/?provider=ACM02&parent=Area/Device01"')
        self.assertContains(tag_response, "PV")
        self.assertContains(tag_response, "F4")
        self.assertContains(tag_response, "~&gt;")
        self.assertNotContains(tag_response, "[~&gt;]")
        self.assertContains(tag_response, 'data-sim-field-name="min_value"')
        self.assertContains(tag_response, 'data-sim-field-name="max_value"')
        self.assertContains(tag_response, 'data-sim-field-name="initial_value"')
        self.assertNotContains(tag_response, 'data-sim-mode-fields="estimate_live"')
        self.assertNotContains(tag_response, 'data-sim-mode-fields="estimate_history"')

    def test_selection_display_checks_ancestor_when_entire_subtree_is_selected(self):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")
        replace_imported_selection("Tag_02", ["Area/Device01"])

        response = self.client.get("/sim/?card=sim-output&mode=detail&provider=Tag_02")

        self.assertContains(response, 'value="Area"')
        self.assertContains(response, 'data-indeterminate="0"')
        self.assertContains(response, 'checked')

    def test_sim_output_tree_search_returns_matching_lazy_nodes(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="ACM02")

        response = self.client.get("/sim/imported/tree/children/", {"provider": "ACM02", "q": "Device01"})

        self.assertContains(response, "Device01")
        self.assertContains(response, "◆")
        self.assertNotContains(response, "/admin/base/simdevicetag/")

    def test_imported_atomic_data_type_icons_are_ascii(self):
        self.assertEqual(data_type_icon("Boolean"), "TF")
        self.assertEqual(data_type_icon("", True), "TF")
        self.assertEqual(data_type_icon("", 4012), "I4")
        self.assertEqual(data_type_icon("", 12.5), "F8")
        self.assertEqual(data_type_icon("Float4"), "F4")
        self.assertEqual(data_type_icon("Float8"), "F8")
        self.assertEqual(data_type_icon("Int2"), "I2")
        self.assertEqual(data_type_icon("String"), 'S"')
        self.assertEqual(data_type_icon(""), "??")

    def test_blank_data_type_tree_rows_infer_numeric_controls_from_value(self):
        import_provider_json_bytes(json.dumps(blank_data_type_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.get("/sim/imported/tree/children/", {"provider": "Tag_02", "parent": "Area"})

        self.assertContains(response, "PAD_FLOW_RATE")
        self.assertContains(response, "I4")
        self.assertContains(response, "Memory|Expr")
        self.assertNotContains(response, "R[]")
        self.assertNotContains(response, 'data-sim-mode-fields="random_range"')
        self.assertNotContains(response, 'data-sim-mode-fields="sin_range"')
        self.assertNotContains(response, 'data-sim-field-name="min_value"')

    def test_blank_value_source_atomic_leaves_do_not_materialize_to_sim_output(self):
        import_provider_json_bytes(json.dumps(blank_data_type_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area"],
                "selection_enabled": ["1"],
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        self.assertEqual(selected_source_paths("Tag_02"), [])
        self.assertFalse(TagConfig.objects.filter(source_path="Area/PAD_FLOW_RATE", materialized=True).exists())

    def test_udt_instance_leaf_rows_inherit_type_definition_metadata(self):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.get("/sim/imported/tree/children/", {"provider": "Tag_02", "parent": "Area/Device01"})

        self.assertContains(response, "Demand_Poll_eACM")
        self.assertContains(response, "TF")
        self.assertContains(response, "Ref")
        self.assertNotContains(response, "?01")
        self.assertNotContains(response, 'data-sim-mode-fields="static"')
        self.assertNotContains(response, 'data-sim-field-name="initial_value"')
        self.assertNotContains(response, "R[]")
        self.assertNotContains(response, 'data-sim-mode-fields="sin_range"')

    def test_provider_tree_children_batches_selection_and_metadata_queries(self):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")
        replace_imported_selection("Tag_02", ["Area/Device01/Demand_Poll_eACM"])

        with CaptureQueriesContext(connection) as queries:
            tree = base_provider_tree_children("Tag_02", "Area/Device01")

        self.assertIn("Demand_Poll_eACM", {node.name for node in tree.nodes})
        self.assertLessEqual(len(queries), 8)

    def test_start_simulation_unselects_descendant_selections(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="ACM02")
        replace_imported_selection("ACM02", ["Area", "Area/Device01"])

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "ACM02",
                "selection_paths": ["Area"],
                "selection_enabled": ["0"],
                "selection_modes": ["estimate_live"],
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=ACM02", fetch_redirect_response=False)
        run_next_sim_job()
        self.assertEqual(selected_source_paths("ACM02"), [])

    def test_start_simulation_stores_selection_without_flat_materialization(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01"],
                "selection_enabled": ["1"],
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        selection = TagSelection.objects.get(provider__name="Tag_02", path="Area/Device01")
        self.assertEqual(selection.config, {})
        self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/PV", materialized=True).exists())

    def test_apply_selection_post_enqueues_without_mutating_selection_state(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01"],
                "selection_enabled": ["1"],
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        self.assertFalse(TagSelection.objects.filter(provider__name="Tag_02").exists())
        self.assertEqual(selected_source_paths("Tag_02"), [])

    @patch("fluxy.Fluxy")
    def test_start_simulation_rehydrates_selected_tree_when_requested(self, fluxy_class):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")
        fake_fx = FakeFluxy()
        fluxy_class.return_value = fake_fx

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01"],
                "selection_enabled": ["1"],
                "rehydrate": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        self.assertTrue(fake_fx.tag.configured)
        self.assertEqual(fake_fx.tag.configured[-1]["base_path"], "[Tag_02]")
        self.assertEqual(fake_fx.tag.configured[-1]["tags"][0]["name"], "Area")

    @patch("fluxy.Fluxy")
    def test_start_simulation_deletes_rehydrated_branch_when_selection_removed(self, fluxy_class):
        import_provider_json_bytes(json.dumps(udt_opc_provider_fixture()).encode("utf-8"), provider_name="Tag_02")
        fake_fx = FakeFluxy()
        fluxy_class.return_value = fake_fx
        endpoint = FieldEndpoint.objects.create(name="Flux sim ACM_02 Server")
        device = create_device_config(
            endpoint=endpoint,
            name="Device01",
            device_type="Rehydrated UDT Backing",
        )
        create_tag_config(
            device=device,
            name="CommStatus",
            data_type=Tag.DataType.INT,
            source_path="Area/Device01/CommStatus",
            materialized=True,
            config={"rehydrated_source_path": "Area/Device01/CommStatus"},
        )

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01"],
                "selection_enabled": ["0"],
                "rehydrate": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        self.assertEqual(fake_fx.tag.deleted, [["[Tag_02]Area/Device01"]])
        self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/CommStatus", materialized=True).exists())

    def test_folder_selection_ignores_mode_override_and_uses_typed_default(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01"],
                "selection_enabled": ["1"],
                "selection_modes": ["random_range"],
                "selection_configs": [json.dumps({"simulation_mode": "random_range", "min_value": "3", "max_value": "7"})],
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        self.assertEqual(selected_source_paths("Tag_02"), ["Area/Device01/PV"])
        selection = TagSelection.objects.get(provider__name="Tag_02", path="Area/Device01")
        self.assertEqual(selection.config, {})
        self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/PV", materialized=True).exists())

    def test_start_simulation_stores_range_config_and_materializes_random_range(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01"],
                "selection_enabled": ["1"],
                "default_mode_numeric": "random_range",
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        self.assertEqual(provider_default_modes("Tag_02")["numeric"], "random_range")
        self.assertEqual(selected_source_paths("Tag_02"), ["Area/Device01/PV"])
        selection = TagSelection.objects.get(provider__name="Tag_02", path="Area/Device01")
        self.assertEqual(selection.config, {})
        self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/PV", materialized=True).exists())

    def test_atomic_override_stores_range_config_and_materializes_random_range(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01", "Area/Device01/PV"],
                "selection_enabled": ["1", "1"],
                "selection_modes": ["", "random_range"],
                "selection_configs": ["", json.dumps({"simulation_mode": "random_range", "min_value": "3", "max_value": "7"})],
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        selection = TagSelection.objects.get(provider__name="Tag_02", path="Area/Device01/PV")
        self.assertEqual(selection.config["simulation_mode"], "random_range")
        self.assertEqual(selection.config["min_value"], "3")
        self.assertEqual(selection.config["max_value"], "7")
        self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/PV", materialized=True).exists())

    def test_start_simulation_stores_static_initial_value(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")

        response = self.client.post(
            "/sim/apply-selection/",
            {
                "provider": "Tag_02",
                "selection_paths": ["Area/Device01", "Area/Device01/PV"],
                "selection_enabled": ["1", "1"],
                "selection_modes": ["", "static"],
                "selection_configs": ["", json.dumps({"simulation_mode": "static", "initial_value": "42.5"})],
                "confirm_apply": "1",
            },
        )

        self.assertRedirects(response, "/sim/?card=sim-output&mode=detail&provider=Tag_02", fetch_redirect_response=False)
        run_next_sim_job()
        selection = TagSelection.objects.get(provider__name="Tag_02", path="Area/Device01/PV")
        self.assertEqual(selection.config["simulation_mode"], "static")
        self.assertEqual(selection.config["initial_value"], "42.5")
        self.assertFalse(TagConfig.objects.filter(source_path="Area/Device01/PV", materialized=True).exists())

    def test_apply_selection_materializes_only_selected_imported_tags_and_disables_deselected(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")
        selected_path = "Area/Device01/PV"
        replace_imported_selection("Tag_02", ["Area/Device01"])

        plan = selected_output_plan("Tag_02")
        self.assertEqual(plan.selected_count, 1)
        self.assertEqual(plan.create_count, 1)

        result = apply_selected_output("Tag_02", mode_by_path={selected_path: "sin_range"})

        self.assertEqual(result.created_count, 1)
        field_tag = TagConfig.objects.get(source_path=selected_path, materialized=True)
        self.assertEqual(field_tag.device.browse_path, "Tag_02")
        self.assertEqual(field_tag.device.name, "Device01")
        self.assertEqual(field_tag.simulation_type, TagConfig.SimulationType.WAVE)
        self.assertEqual(field_tag.config["mode_config"]["simulation_mode"], "sin_range")
        self.assertTrue(field_tag.enabled)

        replace_imported_selection("Tag_02", [])
        disabled = apply_selected_output("Tag_02")

        self.assertEqual(disabled.disabled_count, 1)
        field_tag.refresh_from_db()
        self.assertFalse(field_tag.enabled)

    def test_apply_selection_ui_exposes_mode_dropdown_for_new_output_tags(self):
        import_provider_json_bytes(json.dumps(provider_export_fixture()).encode("utf-8"), provider_name="Tag_02")
        replace_imported_selection("Tag_02", ["Area/Device01"])

        response = self.client.get("/sim/", {"card": "sim-output", "mode": "configure", "provider": "Tag_02"})

        self.assertContains(response, "New Output Tags")
        self.assertContains(response, "Estimate from Live")
        self.assertContains(response, "Estimate Polynomial with History")
        self.assertContains(response, "Random Range")
        self.assertContains(response, "Sin Range")
        self.assertContains(response, "Bool Random")
        self.assertContains(response, "Start Simulation")


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
            ProviderSelection.objects.create(provider=provider_row("ACM02"), path="Area")
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
            ProviderSelection.objects.create(provider=provider_row("ACM02"), path="Area/Device01")

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
        ProviderSelection.objects.create(provider=provider_row("ACM02"), path="Area")

        response = self.client.get("/sim/imported/selected-paths.json?provider=ACM02")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["provider"], "ACM02")
        self.assertIn("selected_source_paths", response.json())

    def test_imported_bulk_selection_replaces_provider_paths(self):
        ProviderSelection.objects.create(provider=provider_row("ACM02"), path="Old")
        other_provider = provider_row("Other")
        ProviderSelection.objects.create(provider=other_provider, path="Keep")

        response = self.client.post(
            "/sim/imported/set-bulk/",
            {"provider": "ACM02", "paths": ["Area", "Area/Device01"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(ProviderSelection.objects.filter(provider__name="ACM02").values_list("path", flat=True)),
            ["Area", "Area/Device01"],
        )
        self.assertTrue(ProviderSelection.objects.filter(provider=other_provider, path="Keep").exists())

    def test_sim_page_json_import_populates_base_provider(self):
        upload = SimpleUploadedFile(
            "simtag.json",
            json.dumps(provider_export_fixture()).encode("utf-8"),
            content_type="application/json",
        )

        response = self.client.post("/sim/import/json/", {"provider": "simtag", "provider_json": upload})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SimJob.objects.filter(kind=SimJob.Kind.IMPORT_PROVIDER_JSON).count(), 1)
        run_next_sim_job()
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
        with patch("fluxy.Fluxy", return_value=fake_fx) as fluxy_class:
            response = self.client.post(
                "/sim/import/ignition/",
                {"source_provider": "simtag", "provider": "simtag"},
            )
            run_next_sim_job()

        self.assertEqual(response.status_code, 302)
        fluxy_class.assert_called_once()
        self.assertTrue(TagProvider.objects.filter(name="simtag", source=TagProvider.Source.IGNITION_PROVIDER).exists())
        self.assertTrue(TagNode.objects.filter(provider__name="simtag", path="Area/Device01/PV").exists())

    def test_sim_page_remove_ignition_tags_uses_fluxy_delete(self):
        fake_fx = FakeFluxy()
        with patch("fluxy.Fluxy", return_value=fake_fx):
            response = self.client.post(
                "/sim/remove-ignition-tags/",
                {"provider": "testsim", "folder_path": "FluxSim"},
            )
            run_next_sim_job()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(fake_fx.tag.deleted, [["[testsim]FluxSim"]])

    def test_rehydration_plan_preserves_paths_and_rewrites_udt_provider(self):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")
        replace_imported_selection("Tag_02", ["Area/Device01"])

        plan = build_rehydration_plan("Tag_02", target_provider="tagsim")

        self.assertEqual(plan.tag_base_path, "[tagsim]")
        self.assertGreater(plan.udt_dependency_count, 0)
        area = find_config(plan.tag_configs, ["Area"])
        device = find_config(plan.tag_configs, ["Area", "Device01"])
        udt_type = find_config(plan.tag_configs, ["_types_", "Device", "SP", "RTU"])
        udt_child = find_config(plan.tag_configs, ["_types_", "Device", "SP", "RTU", "Demand_Poll_eACM"])

        self.assertEqual(area["tagType"], "Folder")
        self.assertEqual(device["tagType"], "UdtInstance")
        self.assertEqual(device["typeId"], "[tagsim]_types_/Device/SP/RTU")
        self.assertEqual(device["parameters"]["OPC_Server"]["value"], "Flux Field Flux_sim_ACM_02_Server")
        self.assertEqual(udt_type["tagType"], "UdtType")
        self.assertEqual(udt_child["tagType"], "AtomicTag")
        self.assertEqual(udt_child["dataType"], "Boolean")

    def test_rehydration_plan_defaults_target_to_source_and_preserves_type_id(self):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        plan = build_rehydration_plan("Tag_02", selected_paths=["Area/Device01"])
        device = find_config(plan.tag_configs, ["Area", "Device01"])

        self.assertEqual(plan.target_provider, "Tag_02")
        self.assertEqual(plan.tag_base_path, "[Tag_02]")
        self.assertEqual(device["typeId"], "[Tag_02]_types_/Device/SP/RTU")

    def test_rehydration_plan_qualifies_relative_type_id_to_provider_types(self):
        import_provider_json_bytes(json.dumps(relative_type_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        plan = build_rehydration_plan("Tag_02", selected_paths=["Area/Pad01"])
        pad = find_config(plan.tag_configs, ["Area", "Pad01"])

        self.assertEqual(pad["typeId"], "[Tag_02]_types_/Pad/Pad")

    def test_rehydration_apply_uses_target_provider_base_path(self):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")
        plan = build_rehydration_plan("Tag_02", target_provider="tagsim", selected_paths=["Area/Device01"])
        fake_fx = FakeFluxy()

        apply_rehydration_plan(fake_fx, plan, collision_policy="m")

        self.assertEqual(fake_fx.tag.configured[0]["base_path"], "[tagsim]")
        self.assertEqual(fake_fx.tag.configured[0]["tags"], [{"name": "_types_", "tagType": "Folder"}])
        self.assertEqual(fake_fx.tag.configured[1]["base_path"], "[tagsim]_types_")
        self.assertEqual(fake_fx.tag.configured[1]["tags"][0]["name"], "Device")
        self.assertEqual(fake_fx.tag.configured[2]["base_path"], "[tagsim]")
        self.assertEqual(fake_fx.tag.configured[2]["tags"][0]["name"], "Area")
        self.assertEqual(fake_fx.tag.configured[0]["collision_policy"], "m")

    def test_rehydration_backing_materializes_udt_opc_members_for_fieldagent(self):
        import_provider_json_bytes(json.dumps(udt_opc_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        result = materialize_rehydration_backing("Tag_02", selected_paths=["Area/Device01"])

        self.assertEqual(result.endpoint_count, 1)
        self.assertEqual(result.device_count, 1)
        self.assertEqual(result.tag_count, 3)
        endpoint = FieldEndpoint.objects.get(name="Flux sim ACM_02 Server")
        device = DeviceConfig.objects.get(endpoint=endpoint, base_device__name="Device01")
        self.assertEqual(TagConfig.objects.get(sim_device=device, tag_name="CommStatus").node_id, "ns=2;s=Device01.CommStatus")
        self.assertEqual(TagConfig.objects.get(sim_device=device, tag_name="Running").data_type, Tag.DataType.BOOL)
        self.assertEqual(TagConfig.objects.get(sim_device=device, tag_name="31060F").node_id, "ns=2;s=Device01.31060F")

    def test_rehydration_rewrites_unavailable_tag_groups_to_default(self):
        import_provider_json_bytes(json.dumps(udt_opc_provider_fixture()).encode("utf-8"), provider_name="Tag_02")

        plan = build_rehydration_plan("Tag_02", selected_paths=["Area/Device01"])
        pressure_diff = find_config(plan.tag_configs, ["_types_", "Device", "SP", "RTU", "PressureDiff"])

        self.assertEqual(pressure_diff["tagGroup"], "Default")

    @patch("flux.sim.management.commands.rehydrate_tag_provider_selection.fluxy.Fluxy")
    def test_rehydrate_command_applies_selected_tree_to_target_provider(self, fluxy_class):
        import_provider_json_bytes(json.dumps(udt_inherited_provider_fixture()).encode("utf-8"), provider_name="Tag_02")
        fake_fx = FakeFluxy()
        fluxy_class.return_value = fake_fx
        output = StringIO()

        call_command(
            "rehydrate_tag_provider_selection",
            "Tag_02",
            "--target-provider",
            "tagsim",
            "--selected-path",
            "Area/Device01",
            stdout=output,
        )

        fluxy_class.assert_called_once()
        self.assertEqual(fake_fx.tag.configured[0]["base_path"], "[tagsim]")
        self.assertEqual(fake_fx.tag.configured[1]["base_path"], "[tagsim]_types_")
        self.assertEqual(fake_fx.tag.configured[2]["tags"][0]["name"], "Area")
        self.assertIn("Rehydrated", output.getvalue())


class FakeFluxy:
    def __init__(self):
        self.tag = FakeTagApi()


class FakeTagApi:
    def __init__(self):
        self.configured = []
        self.deleted = []

    def configure(self, tags, base_path=None, collision_policy="o"):
        self.configured.append({"tags": tags, "base_path": base_path, "collision_policy": collision_policy})
        return []

    def delete_tags(self, tag_paths):
        self.deleted.append(tag_paths)
        return ["Good" for _path in tag_paths]


def find_config(configs, path_parts):
    current = configs
    found = None
    for part in path_parts:
        found = next(config for config in current if config["name"] == part)
        current = found.get("tags") or []
    return found


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


def blank_data_type_provider_fixture():
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "PAD_FLOW_RATE",
                        "tagType": "AtomicTag",
                        "valueSource": "memory",
                        "expression": 'runScript("Pad.getFlowRate",0,{Site_Id})',
                        "value": 4012,
                    }
                ],
            }
        ],
    }


def udt_inherited_provider_fixture():
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "_types_",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device",
                        "tagType": "Folder",
                        "tags": [
                            {
                                "name": "SP",
                                "tagType": "Folder",
                                "tags": [
                                    {
                                        "name": "RTU",
                                        "tagType": "UdtType",
                                        "tags": [
                                            {
                                                "name": "Demand_Poll_eACM",
                                                "tagType": "AtomicTag",
                                                "dataType": "Boolean",
                                                "valueSource": "reference",
                                                "sourceTagPath": {
                                                    "binding": "[MQTT Engine]Edge Nodes/{MQTTGroupID}/{MQTTNodeID}/{MQTTDeviceID}/Demand",
                                                    "bindType": "parameter",
                                                },
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device01",
                        "tagType": "UdtInstance",
                        "typeId": "[Tag_02]_types_/Device/SP/RTU",
                        "parameters": {
                            "OPC_Server": {"value": "ACM_02", "dataType": "String"},
                            "OPC_Device": {"value": "Device01", "dataType": "String"},
                        },
                        "tags": [
                            {
                                "name": "Demand_Poll_eACM",
                                "tagType": "AtomicTag",
                            }
                        ],
                    }
                ],
            },
        ],
    }


def relative_type_provider_fixture():
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "_types_",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Pad",
                        "tagType": "Folder",
                        "tags": [
                            {
                                "name": "Pad",
                                "tagType": "UdtType",
                                "tags": [{"name": "PV", "tagType": "AtomicTag", "dataType": "Float4"}],
                            }
                        ],
                    }
                ],
            },
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Pad01",
                        "tagType": "UdtInstance",
                        "typeId": "Pad/Pad",
                        "tags": [{"name": "PV", "tagType": "AtomicTag", "value": 12.5}],
                    }
                ],
            },
        ],
    }


def udt_opc_provider_fixture():
    return {
        "name": "Tag_02",
        "tagType": "Provider",
        "tags": [
            {
                "name": "_types_",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device",
                        "tagType": "Folder",
                        "tags": [
                            {
                                "name": "SP",
                                "tagType": "Folder",
                                "tags": [
                                    {
                                        "name": "RTU",
                                        "tagType": "UdtType",
                                        "parameters": {
                                            "OPC_Server": {"value": "ACM_02", "dataType": "String"},
                                            "OPC_Device": {"dataType": "String"},
                                            "OPC_Prefix": {"value": "ns=2;s=", "dataType": "String"},
                                            "IO_Address": {"value": 31000, "dataType": "Integer"},
                                        },
                                        "tags": [
                                            {
                                                "name": "CommStatus",
                                                "tagType": "AtomicTag",
                                                "dataType": "Int4",
                                                "valueSource": "opc",
                                                "opcServer": {"binding": "{OPC_Server}", "bindType": "parameter"},
                                                "opcItemPath": {
                                                    "binding": "{OPC_Prefix}{OPC_Device}.{TagName}",
                                                    "bindType": "parameter",
                                                },
                                            },
                                            {
                                                "name": "Running",
                                                "tagType": "AtomicTag",
                                                "dataType": "Boolean",
                                                "valueSource": "opc",
                                                "opcServer": {"binding": "{OPC_Server}", "bindType": "parameter"},
                                                "opcItemPath": {
                                                    "binding": "{OPC_Prefix}{OPC_Device}.{TagName}",
                                                    "bindType": "parameter",
                                                },
                                            },
                                            {
                                                "name": "PressureDiff",
                                                "tagType": "AtomicTag",
                                                "dataType": "Float4",
                                                "tagGroup": "Tubing_Casing",
                                                "valueSource": "opc",
                                                "opcServer": {"binding": "{OPC_Server}", "bindType": "parameter"},
                                                "opcItemPath": {
                                                    "binding": "{OPC_Prefix}{OPC_Device}.{IO_Address+24}F",
                                                    "bindType": "parameter",
                                                },
                                            },
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "name": "Area",
                "tagType": "Folder",
                "tags": [
                    {
                        "name": "Device01",
                        "tagType": "UdtInstance",
                        "typeId": "[Tag_02]_types_/Device/SP/RTU",
                        "parameters": {
                            "OPC_Server": {"value": "ACM_02", "dataType": "String"},
                            "OPC_Device": {"value": "Device01", "dataType": "String"},
                            "IO_Address": {"value": 31036, "dataType": "String"},
                        },
                    }
                ],
            },
        ],
    }
