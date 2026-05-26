from __future__ import annotations

import csv
import zipfile
from datetime import timedelta
from io import BytesIO
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from flux.base.runtime import LatestTagValue, RuntimeTag, TagSample, TagSchedule
from flux.plane.models import Sample
from flux.plane.services import ensure_series_for_full_path
from flux.trace.models import TraceProfile, TraceSignal

from .models import Bundle, Cell, Comment, Point, Relationship, Source, Visual
from .services import (
    import_cell_bundle_path,
    live_scope_rows,
    seed_demo_cell_bundle,
    trace_scope_rows,
)


class CellCsvBundleTests(TestCase):
    def test_cell_models_use_dedicated_postgres_schema_tables(self) -> None:
        self.assertEqual(Bundle._meta.db_table, '"cell"."bundle"')
        self.assertEqual(Cell._meta.db_table, '"cell"."cell"')
        self.assertEqual(Point._meta.db_table, '"cell"."point"')
        self.assertEqual(Relationship._meta.db_table, '"cell"."relationship"')
        self.assertEqual(Source._meta.db_table, '"cell"."source"')
        self.assertEqual(Visual._meta.db_table, '"cell"."visual"')
        self.assertEqual(Comment._meta.db_table, '"cell"."comment"')

    def test_import_cell_bundle_creates_bundle_cells_and_points(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bundle_dir = write_bundle_fixture(Path(temp_dir))
            result = import_cell_bundle_path(bundle_dir)

        self.assertEqual(result.bundles, 1)
        self.assertEqual(result.cells, 2)
        self.assertEqual(result.points, 3)
        self.assertEqual(result.relationships, 1)
        self.assertEqual(Bundle.objects.get().key, "test-pad")
        self.assertEqual(Cell.objects.get(slug="well-01").kind, "Well")
        self.assertEqual(
            Point.objects.get(key="tubing-pressure").full_path,
            "[default]Sites/A/Well_01/TubingPressure",
        )
        self.assertEqual(Relationship.objects.get().relationship_type, "next_area")

    def test_import_cell_bundle_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bundle_dir = write_bundle_fixture(Path(temp_dir))
            import_cell_bundle_path(bundle_dir)
            import_cell_bundle_path(bundle_dir)

        self.assertEqual(Bundle.objects.count(), 1)
        self.assertEqual(Cell.objects.count(), 2)
        self.assertEqual(Point.objects.count(), 3)
        self.assertEqual(Relationship.objects.count(), 1)

    def test_live_and_trace_rows_match_existing_csv_contracts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))

        live_rows = live_scope_rows("test-pad")
        trace_rows = trace_scope_rows("test-pad")

        self.assertEqual(live_rows[0]["scope"], "test-pad")
        self.assertEqual(live_rows[0]["card"], "Well 01")
        self.assertEqual(live_rows[0]["full_path"], "[default]Sites/A/Well_01/TubingPressure")
        self.assertEqual(trace_rows[0]["Chart Scope"], "test-pad-well-01")
        self.assertEqual(trace_rows[0]["Tag 1"], "[default]Sites/A/Well_01/TubingPressure")

    def test_export_command_writes_live_and_trace_csvs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            import_cell_bundle_path(write_bundle_fixture(root))
            output_dir = root / "exports"
            call_command(
                "export_cell_csv_bundle", "test-pad", "--output", str(output_dir), stdout=StringIO()
            )

            live_rows = list(csv.DictReader((output_dir / "live_scope.csv").open(encoding="utf-8")))
            trace_rows = list(
                csv.DictReader((output_dir / "trace_scopes.csv").open(encoding="utf-8"))
            )
            cell_rows = list(csv.DictReader((output_dir / "cells.csv").open(encoding="utf-8")))
            relationship_rows = list(
                csv.DictReader((output_dir / "relationships.csv").open(encoding="utf-8"))
            )

        self.assertEqual(live_rows[0]["scope"], "test-pad")
        self.assertEqual(trace_rows[0]["Chart Scope"], "test-pad-well-01")
        self.assertEqual(cell_rows[0]["bundle"], "test-pad")
        self.assertEqual(relationship_rows[0]["relationship"], "next_area")

    def test_csv_download_endpoints_return_csv(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))

        response = self.client.get("/cell/api/bundles/test-pad/live-scope.csv")
        relationships = self.client.get("/cell/api/bundles/test-pad/relationships.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("scope,scope_name", response.content.decode("utf-8"))
        self.assertEqual(relationships.status_code, 200)
        self.assertIn(
            "from_cell_slug,relationship,to_cell_slug", relationships.content.decode("utf-8")
        )

    def test_zip_upload_imports_cell_bundle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bundle_dir = write_bundle_fixture(Path(temp_dir))
            upload = SimpleUploadedFile(
                "cells.zip", zip_bundle(bundle_dir), content_type="application/zip"
            )

        response = self.client.post("/cell/import/", {"bundle_zip": upload}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Imported 2 cells and 3 points")
        self.assertEqual(Bundle.objects.get().source_name, "cells.zip")
        self.assertEqual(Relationship.objects.count(), 1)

    def test_cell_page_renders_process_cards_relationships_and_comments(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))
        cell = Cell.objects.get(slug="well-01")
        Comment.objects.create(cell=cell, body="Seal pressure rising", author_name="Sam")

        response = self.client.get("/cell/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flux.cell process cards")
        self.assertContains(response, "Well 01")
        self.assertContains(response, "Tubing Pressure")
        self.assertContains(response, "Tank 01")
        self.assertContains(response, "Seal pressure rising")
        self.assertContains(response, "Seed Demo Cell")

    def test_cell_bundle_table_uses_ten_row_server_side_htmx_pagination(self) -> None:
        for index in range(12):
            Bundle.objects.create(key=f"bundle-{index:02d}", name=f"Bundle {index:02d}")

        first_page = self.client.get("/cell/")
        second_page = self.client.get("/cell/", {"bundles_page": "2"})

        self.assertContains(first_page, "Showing 1-10 of 12 bundles")
        self.assertContains(first_page, 'hx-target="#cell-bundles-panel"')
        self.assertContains(first_page, "bundles_page=2")
        self.assertContains(first_page, "Bundle 09")
        self.assertNotContains(first_page, "Bundle 10")
        self.assertContains(second_page, "Showing 11-12 of 12 bundles")
        self.assertContains(second_page, "Bundle 10")
        self.assertNotContains(second_page, "Bundle 09")

    def test_cell_page_does_not_render_phone_swipe_simulator(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))

        response = self.client.get("/cell/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-cell-phone-simulator")
        self.assertNotContains(response, "Swipe right for next")

    def test_phone_demo_renders_only_swipe_cards(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))

        response = self.client.get("/cell/phone-demo/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-cell-phone-simulator")
        self.assertContains(response, "Flux Home")
        self.assertContains(response, 'class="cell-phone-home-link"')
        self.assertContains(response, "cell-phone-card-topline")
        self.assertNotContains(response, "Swipe right for next. Swipe left for previous.")
        self.assertNotContains(response, "Demo Area")
        self.assertNotContains(response, "data-cell-phone-counter")
        self.assertContains(response, 'data-cell-phone-nav="next"')
        self.assertContains(response, 'data-cell-phone-nav="prev"')
        self.assertContains(response, "data-cell-phone-chart")
        self.assertContains(response, "Trace Chart")
        self.assertNotContains(response, "Showing 1 of 2: Well 01")
        self.assertContains(response, 'data-cell-target-id="cell-test-pad-well-01"')
        self.assertContains(response, 'data-cell-target-id="cell-test-pad-tank-01"')
        self.assertNotContains(response, "Process Collections")
        self.assertNotContains(response, "Import Spreadsheet Bundle")
        self.assertNotContains(response, "data-flux-cell-card")
        self.assertNotContains(response, 'class="site-header"')

    def test_phone_demo_renders_trace_sparkline_from_cached_samples(self) -> None:
        seed_demo_cell_bundle()

        response = self.client.get("/cell/phone-demo/")

        self.assertContains(response, 'class="cell-phone-chart-series cell-phone-chart-series-1"')
        self.assertContains(response, "Pressure · 3 samples · plane samples")
        self.assertContains(response, "47.250")

    def test_cell_page_uses_cached_runtime_values_and_samples(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))
        schedule = TagSchedule.objects.create(name="cell-fast", interval_seconds=1)
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Sites/A/Well_01/TubingPressure",
            display_name="Tubing Pressure",
            engineering_units="psi",
            schedule=schedule,
        )
        now = timezone.now()
        LatestTagValue.objects.create(
            tag=tag, value=525.1239, quality_code="Good", value_timestamp=now, read_at=now
        )
        for index, value in enumerate((510.0, 520.0, 525.1239)):
            TagSample.objects.create(
                tag=tag,
                value=value,
                quality_code="Good",
                value_timestamp=now,
                read_at=now + timedelta(seconds=index),
            )

        response = self.client.get("/cell/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "525.123")
        self.assertContains(response, "psi")
        self.assertContains(response, "3 samples")
        self.assertContains(response, "runtime samples")

    def test_cell_page_prefers_plane_samples_for_chart_signals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))
        schedule = TagSchedule.objects.create(name="cell-trace", interval_seconds=1)
        tag = RuntimeTag.objects.create(
            provider="default",
            path="Sites/A/Well_01/TubingPressure",
            display_name="Tubing Pressure",
            engineering_units="psi",
            schedule=schedule,
        )
        now = timezone.now()
        LatestTagValue.objects.create(
            tag=tag, value=525.1239, quality_code="Good", value_timestamp=now, read_at=now
        )
        TagSample.objects.create(
            tag=tag, value=111.0, quality_code="Good", value_timestamp=now, read_at=now
        )
        profile = TraceProfile.objects.create(key="cell-test", label="Cell Test")
        series = ensure_series_for_full_path(tag.full_path)
        signal = TraceSignal.objects.create(
            profile=profile, tag=tag, series=series, label="Tubing Pressure", sort_order=1
        )
        Sample.objects.create(series=signal.series, timestamp=now, value_float=540.0)

        response = self.client.get("/cell/")

        self.assertContains(response, "plane samples")
        self.assertContains(response, "540.000")

    def test_seed_demo_command_creates_idempotent_runtime_backed_sample(self) -> None:
        output = StringIO()

        call_command("seed_cell_demo", stdout=output)
        call_command("seed_cell_demo", stdout=StringIO())

        self.assertIn("/cell/#cell-demo-pad-pump-101", output.getvalue())
        self.assertEqual(Bundle.objects.get(key="demo-pad").cells.count(), 2)
        self.assertEqual(Point.objects.count(), 4)
        self.assertEqual(Relationship.objects.count(), 3)
        self.assertEqual(Comment.objects.count(), 1)
        self.assertEqual(RuntimeTag.objects.filter(path__startswith="Demo/").count(), 4)
        self.assertEqual(TagSample.objects.count(), 10)
        self.assertEqual(TraceSignal.objects.count(), 3)
        self.assertEqual(Sample.objects.count(), 9)

        response = self.client.get("/cell/")

        self.assertContains(response, "Pump 101")
        self.assertContains(response, "Tank 101")
        self.assertContains(response, "47.250")
        self.assertContains(response, "73.400")
        self.assertContains(response, "plane samples")

    def test_seed_demo_service_can_skip_runtime_cache(self) -> None:
        result = seed_demo_cell_bundle(include_runtime=False)

        self.assertEqual(result.runtime_tags, 0)
        self.assertEqual(result.plane_sample_points, 0)
        self.assertEqual(Cell.objects.count(), 2)
        self.assertEqual(RuntimeTag.objects.count(), 0)

    def test_seed_demo_endpoint_redirects_to_sample_cell(self) -> None:
        response = self.client.post("/cell/seed-demo/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/cell/#cell-demo-pad-pump-101")
        self.assertEqual(Cell.objects.count(), 2)
        self.assertEqual(RuntimeTag.objects.filter(path__startswith="Demo/").count(), 4)

    def test_add_comment_posts_latest_cell_comment(self) -> None:
        with TemporaryDirectory() as temp_dir:
            import_cell_bundle_path(write_bundle_fixture(Path(temp_dir)))

        response = self.client.post(
            "/cell/bundles/test-pad/cells/well-01/comments/",
            {"body": "Operator checked pump seal", "author_name": "Dana"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        comment = Comment.objects.get()
        self.assertEqual(comment.body, "Operator checked pump seal")
        self.assertContains(response, "Operator checked pump seal")


def write_bundle_fixture(root: Path) -> Path:
    bundle_dir = root / "cell-bundle"
    bundle_dir.mkdir(exist_ok=True)
    (bundle_dir / "cells.csv").write_text(
        "bundle,bundle_name,cell_slug,name,group,kind,description,sort_order,enabled\n"
        "test-pad,Test Pad,well-01,Well 01,Pad A,Well,First draft well cell,1,true\n"
        "test-pad,Test Pad,tank-01,Tank 01,Pad A,Tank,First draft tank cell,2,true\n",
        encoding="utf-8",
    )
    (bundle_dir / "points.csv").write_text(
        "bundle,cell_slug,key,label,full_path,role,engineering_units,include_live,include_trace,live_order,trace_order,axis_key,range_min,range_max,color,enabled\n"
        "test-pad,well-01,tubing-pressure,Tubing Pressure,[default]Sites/A/Well_01/TubingPressure,pv,psi,true,true,1,1,pressure,0,1200,#35a7ff,true\n"
        "test-pad,well-01,running,Running,[default]Sites/A/Well_01/Running,status,,true,false,2,0,,,,true\n"
        "test-pad,tank-01,level,Level,[default]Sites/A/Tank_01/Level,pv,%,true,true,1,1,level,0,100,#67e8f9,true\n",
        encoding="utf-8",
    )
    (bundle_dir / "relationships.csv").write_text(
        "bundle,from_cell_slug,relationship,to_cell_slug,label,sort_order,enabled\n"
        "test-pad,well-01,next_area,tank-01,Next Area,1,true\n",
        encoding="utf-8",
    )
    return bundle_dir


def zip_bundle(bundle_dir: Path) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for filename in ("cells.csv", "points.csv", "relationships.csv"):
            archive.write(bundle_dir / filename, filename)
    return buffer.getvalue()
