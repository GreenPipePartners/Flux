from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from .models import HmiParameterFact, HmiScreenFact, HmiTagReferenceFact, MineRun, PlcControllerFact, PlcTagFact


class MinePersistenceTests(TestCase):
    def test_flux_mine_source_persists_l5x_plc_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "sample.L5X"
            source.write_text(
                """
                <RSLogix5000Content>
                  <Controller Name="PLC_01" ProcessorType="1756-L83E" MajorRev="35">
                    <DataTypes>
                      <DataType Name="ValveT">
                        <Members>
                          <Member Name="Cmd" DataType="BOOL" />
                        </Members>
                      </DataType>
                    </DataTypes>
                    <Tags>
                      <Tag Name="Valve_01" TagType="Base" DataType="ValveT" />
                      <Tag Name="Samples" TagType="Base" DataType="REAL" Dimensions="20" />
                    </Tags>
                  </Controller>
                </RSLogix5000Content>
                """.strip(),
                encoding="utf-8",
            )

            call_command("flux_mine_source", str(source), stdout=StringIO())

        run = MineRun.objects.get()
        self.assertEqual(run.status, MineRun.Status.COMPLETE)
        self.assertEqual(run.source_type, MineRun.SourceType.PLC_L5X)
        self.assertEqual(run.summary["controller_count"], 1)
        self.assertEqual(PlcControllerFact.objects.get().name, "PLC_01")
        self.assertEqual(PlcTagFact.objects.count(), 2)
        self.assertEqual(PlcTagFact.objects.get(name="Samples").array_dimensions, [20])

    def test_flux_mine_source_persists_factorytalk_hmi_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Screens").mkdir()
            (root / "Screens" / "Overview.xml").write_text(
                """
                <gfx>
                  <displaySettings width="800" height="600" />
                  <numericDisplay name="Pressure" left="10" top="20" tag="{[PLC]PT001.PV}" />
                </gfx>
                """.strip(),
                encoding="utf-8",
            )
            (root / "Overview.par").write_text("#1=[PLC]PT001\n", encoding="utf-8")

            call_command("flux_mine_source", str(root), "--source-type", "factorytalk", stdout=StringIO())

        run = MineRun.objects.get()
        self.assertEqual(run.status, MineRun.Status.COMPLETE)
        self.assertEqual(run.source_type, MineRun.SourceType.FACTORYTALK)
        self.assertEqual(HmiScreenFact.objects.count(), 1)
        self.assertEqual(HmiTagReferenceFact.objects.get().base_tag, "PT001")
        self.assertEqual(HmiParameterFact.objects.get().name, "p1")
