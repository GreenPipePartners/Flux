from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from flux.mine.models import MineRun

from .models import BuildArtifact, BuildRun


class BuildPersistenceTests(TestCase):
    def test_flux_build_ignition_tags_writes_artifact_from_mine_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "sample.L5X"
            output = root / "artifacts" / "provider.json"
            source.write_text(
                """
                <RSLogix5000Content>
                  <Controller Name="PLC_01" ProcessorType="1756-L83E" MajorRev="35">
                    <Tags>
                      <Tag Name="Pressure" TagType="Base" DataType="REAL" />
                    </Tags>
                  </Controller>
                </RSLogix5000Content>
                """.strip(),
                encoding="utf-8",
            )
            call_command("flux_mine_source", str(source), stdout=StringIO())
            mine_run = MineRun.objects.get()

            call_command("flux_build_ignition_tags", mine_run.id, "--output", str(output), stdout=StringIO())

            payload = json.loads(output.read_text(encoding="utf-8"))

        build_run = BuildRun.objects.get()
        self.assertEqual(build_run.status, BuildRun.Status.COMPLETE)
        self.assertEqual(BuildArtifact.objects.get().kind, "ignition_provider_json")
        self.assertEqual(payload["tagType"], "Provider")
        self.assertIn("_types_", {tag["name"] for tag in payload["tags"]})
        self.assertEqual(build_run.output_bytes, len(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")) + 1)
