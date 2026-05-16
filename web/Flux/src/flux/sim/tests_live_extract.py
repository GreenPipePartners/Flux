from django.test import SimpleTestCase

from flux.sim.live_extract import (
    LiveTagHistoryPoint,
    atomic_tag_names,
    normalize_db_type,
    historical_path,
    rename_root_folder,
    rows_to_history_points,
    tag_path,
    trial_history_paths,
    trial_tag_paths,
)


class LiveExtractTests(SimpleTestCase):
    def test_paths_match_fluxy_historian_shape(self):
        self.assertEqual(tag_path(provider="default", folder="Live", tag_name="Pressure"), "[default]Live/Pressure")
        self.assertEqual(
            historical_path(provider="default", folder="Live", tag_name="Pressure"),
            "histprov:Core Historian:/sys:gateway:/prov:default:/tag:Live/Pressure",
        )

    def test_rename_root_folder_preserves_children(self):
        configs = [
            {
                "name": "LiveSource",
                "tagType": "Folder",
                "tags": [{"name": "Pressure", "tagType": "AtomicTag", "dataType": "Float4"}],
            }
        ]

        renamed = rename_root_folder(configs, source_folder="LiveSource", target_folder="SimReplay")

        self.assertEqual(renamed[0]["name"], "SimReplay")
        self.assertEqual(renamed[0]["tags"][0]["name"], "Pressure")

    def test_atomic_tag_names_walk_nested_configs(self):
        names = atomic_tag_names(
            [
                {
                    "name": "Root",
                    "tagType": "Folder",
                    "tags": [
                        {"name": "Pressure", "tagType": "AtomicTag"},
                        {"name": "Nested", "tagType": "Folder", "tags": [{"name": "Rate", "tagType": "AtomicTag"}]},
                    ],
                }
            ]
        )

        self.assertEqual(names, ["Pressure", "Rate"])

    def test_rows_to_history_points_maps_rows_by_path_suffix(self):
        points = rows_to_history_points(
            [
                {"path": "LiveSource/Pressure", "value": 101.5, "quality": "Good", "timestamp": 1778545000000},
                {"path": "LiveSource/Rate", "value": 42.0, "quality": 192, "timestamp": 1778545060000},
            ],
            tag_names=["Pressure", "Rate"],
        )

        self.assertEqual(
            points,
            [
                LiveTagHistoryPoint("Pressure", 101.5, 1778545000000, "Good"),
                LiveTagHistoryPoint("Rate", 42.0, 1778545060000, 192),
            ],
        )

    def test_rows_to_history_points_maps_ignition_tall_value_columns(self):
        points = rows_to_history_points(
            [
                {"path": "value_0", "value": 101.5, "quality": 192, "timestamp": 1778545000000},
                {"path": "value_1", "value": 42.0, "quality": 192, "timestamp": 1778545000000},
            ],
            tag_names=["Pressure", "Rate"],
        )

        self.assertEqual(
            points,
            [
                LiveTagHistoryPoint("Pressure", 101.5, 1778545000000, 192),
                LiveTagHistoryPoint("Rate", 42.0, 1778545000000, 192),
            ],
        )

    def test_trial_cleanup_paths_cover_source_and_target(self):
        self.assertEqual(
            trial_tag_paths(provider="default", folders=["Live", "Sim"], tag_names=["Pressure"]),
            ["[default]Live/Pressure", "[default]Sim/Pressure"],
        )
        self.assertEqual(
            trial_history_paths(provider="default", folders=["Live", "Sim"], tag_names=["Pressure"]),
            [
                "histprov:Core Historian:/sys:gateway:/prov:default:/tag:Live/Pressure",
                "histprov:Core Historian:/sys:gateway:/prov:default:/tag:Sim/Pressure",
            ],
        )

    def test_normalize_db_type_supports_cleanup_adapter_selection(self):
        self.assertEqual(normalize_db_type("POSTGRESQL"), "POSTGRES")
        self.assertEqual(normalize_db_type("Postgres"), "POSTGRES")
        self.assertEqual(normalize_db_type("SQL Server"), "MSSQL")
        self.assertEqual(normalize_db_type("SQLite"), "SQLITE")
