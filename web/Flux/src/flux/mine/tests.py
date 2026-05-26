from __future__ import annotations

import zipfile
from io import BytesIO
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from .models import (
    HmiComponentActionFact,
    HmiComponentFact,
    HmiComponentParameterFact,
    HmiComponentStateFact,
    HmiGlobalObjectLinkFact,
    HmiParameterFact,
    HmiScreenFact,
    HmiTagReferenceFact,
    HmiVbaLinkFact,
    MineRun,
    PlcControllerFact,
    PlcInstructionFact,
    PlcProgramFact,
    PlcRoutineFact,
    PlcRungFact,
    PlcScheduledProgramFact,
    PlcTagFact,
    PlcTagReferenceFact,
    PlcTaskFact,
)


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

    def test_flux_mine_source_persists_hello_world_l5x_graph(self) -> None:
        source = repo_root() / "logix_samples" / "hello_world.L5X"

        call_command("flux_mine_source", str(source), stdout=StringIO())

        run = MineRun.objects.get()
        self.assertEqual(run.status, MineRun.Status.COMPLETE)
        self.assertEqual(run.summary["controllers"][0]["program_count"], 1)
        self.assertEqual(run.summary["controllers"][0]["task_count"], 1)
        self.assertEqual(run.summary["controllers"][0]["routine_count"], 1)
        self.assertEqual(run.summary["controllers"][0]["rung_count"], 5)

        controller = PlcControllerFact.objects.get(name="hello_world")
        program = PlcProgramFact.objects.get(controller=controller, name="MainProgram")
        self.assertEqual(program.main_routine_name, "MainRoutine")

        task = PlcTaskFact.objects.get(controller=controller, name="MainTask")
        self.assertEqual(task.task_type, "CONTINUOUS")
        self.assertEqual(task.priority, 10)
        self.assertEqual(task.watchdog, 500)
        scheduled = PlcScheduledProgramFact.objects.get(task=task)
        self.assertEqual(scheduled.program, program)
        self.assertEqual(scheduled.name, "MainProgram")

        routine = PlcRoutineFact.objects.get(program=program, name="MainRoutine")
        self.assertEqual(routine.routine_type, "RLL")
        self.assertEqual(PlcRungFact.objects.filter(routine=routine).count(), 5)
        self.assertEqual(
            PlcRungFact.objects.get(routine=routine, number=4).text,
            "[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ];",
        )
        self.assertEqual(PlcInstructionFact.objects.filter(rung__routine=routine).count(), 12)
        self.assertEqual(PlcTagReferenceFact.objects.filter(rung__routine=routine).count(), 14)
        self.assertEqual(PlcTagReferenceFact.objects.filter(rung__routine=routine, tag__isnull=True).count(), 0)
        done_reference = PlcTagReferenceFact.objects.get(original="hello_TON.DN")
        self.assertEqual(done_reference.tag.name, "hello_TON")
        self.assertEqual(done_reference.member_path, "DN")
        self.assertEqual(done_reference.role, "read")
        self.assertEqual(PlcTagReferenceFact.objects.filter(base_tag="hello_world", role="destination").count(), 2)

        self.assertEqual(PlcTagFact.objects.filter(controller=controller, scope="Global").count(), 0)
        self.assertEqual(PlcTagFact.objects.filter(controller=controller, scope="MainProgram").count(), 6)
        hello = PlcTagFact.objects.get(controller=controller, scope="MainProgram", name="hello")
        self.assertEqual(hello.raw["data"][1]["format"], "String")
        self.assertIn("'hello'", hello.raw["data"][1]["text"])

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

    def test_mine_import_upload_persists_l5x_plc_facts(self) -> None:
        upload = SimpleUploadedFile(
            "upload.L5X",
            b"""
            <RSLogix5000Content>
              <Controller Name="PLC_UPLOAD" ProcessorType="1756-L83E" MajorRev="35">
                <Tags><Tag Name="Pressure" TagType="Base" DataType="REAL" /></Tags>
              </Controller>
            </RSLogix5000Content>
            """.strip(),
        )

        response = self.client.post("/mine/import/", {"source_type": "auto", "source": upload})

        self.assertRedirects(response, "/mine/")
        run = MineRun.objects.get()
        self.assertEqual(run.source_path, "upload.L5X")
        self.assertEqual(run.source_type, MineRun.SourceType.PLC_L5X)
        self.assertEqual(PlcControllerFact.objects.get().name, "PLC_UPLOAD")

    def test_mine_import_upload_persists_l5k_plc_facts(self) -> None:
        upload = SimpleUploadedFile(
            "upload.L5K",
            b"""
            CONTROLLER PLC_L5K
                TAG
                    Pressure : REAL;
                END_TAG
            """.strip(),
        )

        response = self.client.post("/mine/import/", {"source_type": "auto", "source": upload})

        self.assertRedirects(response, "/mine/")
        run = MineRun.objects.get()
        self.assertEqual(run.source_type, MineRun.SourceType.PLC_L5K)
        self.assertEqual(PlcControllerFact.objects.get().name, "PLC_L5K")

    def test_mine_import_upload_persists_factorytalk_zip(self) -> None:
        upload = SimpleUploadedFile(
            "factorytalk.zip",
            zip_bytes(
                {
                    "Displays/Overview.xml": """
                    <gfx>
                      <displaySettings width="800" height="600" />
                      <numericDisplay name="Pressure" left="10" top="20" tag="{[PLC]PT001.PV}" />
                    </gfx>
                    """.strip(),
                    "Parameters/Overview.par": "#1=[PLC]PT001\n",
                    "Graphics/Overview.gfx": "ignored",
                }
            ),
            content_type="application/zip",
        )

        response = self.client.post("/mine/import/", {"source_type": "auto", "source": upload})

        self.assertRedirects(response, "/mine/")
        run = MineRun.objects.get()
        self.assertEqual(run.source_type, MineRun.SourceType.FACTORYTALK)
        self.assertEqual(run.source_path, "factorytalk.zip")
        self.assertEqual(run.summary["import"]["container"], "zip")
        self.assertEqual(run.summary["import"]["recognized_file_count"], 2)
        self.assertEqual(HmiScreenFact.objects.get().source_path, "factorytalk.zip:Displays/Overview.xml")
        self.assertEqual(HmiTagReferenceFact.objects.get().base_tag, "PT001")
        self.assertEqual(HmiParameterFact.objects.get().value, "[PLC]PT001")

    def test_mine_import_upload_rejects_unsafe_factorytalk_zip(self) -> None:
        upload = SimpleUploadedFile("factorytalk.zip", zip_bytes({"../evil.xml": "<gfx />"}), content_type="application/zip")

        response = self.client.post("/mine/import/", {"source_type": "auto", "source": upload}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mine import failed")
        self.assertEqual(MineRun.objects.count(), 0)

    def test_flux_mine_source_persists_enriched_factorytalk_hmi_facts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "Screens").mkdir()
            (root / "Screens" / "Overview.xml").write_text(
                """
                <gfx>
                  <displaySettings width="1280" height="720" />
                  <group name="PumpGroup">
                    <numericDisplay name="Speed" left="10" top="20" width="100" height="30" tag="{[PLC]Pump01.Speed}" />
                    <button name="Start" left="30" top="70" width="80" height="24" exposeToVba="vbaControl">
                      <action type="setToOne" tag="{[PLC]Pump01.StartCmd}" />
                    </button>
                    <multiStateIndicator name="RunState" left="140" top="20" width="90" height="30">
                      <states>
                        <state stateId="1" value="{[PLC]Pump01.Running}" backColor="#00ff00">
                          <caption caption="Running" fontSize="12" color="#ffffff" />
                        </state>
                      </states>
                    </multiStateIndicator>
                    <globalObject name="PumpFaceplate" left="240" top="20" width="100" height="100" linkFile="Global Objects" linkObject="Pump" linkBaseObject="PumpTemplate">
                      <parameters>
                        <parameter name="#1" value="{[PLC]Pump01}" description="Pump root" />
                      </parameters>
                    </globalObject>
                  </group>
                </gfx>
                """.strip(),
                encoding="utf-8",
            )

            call_command("flux_mine_source", str(root), "--source-type", "factorytalk", stdout=StringIO())

        run = MineRun.objects.get()
        self.assertEqual(run.summary["action_count"], 1)
        self.assertEqual(run.summary["state_count"], 1)
        self.assertEqual(run.summary["component_parameter_count"], 1)
        self.assertEqual(run.summary["global_object_link_count"], 1)
        self.assertEqual(run.summary["vba_link_count"], 1)

        group = HmiComponentFact.objects.get(name="PumpGroup")
        speed = HmiComponentFact.objects.get(name="Speed")
        self.assertTrue(group.is_group)
        self.assertEqual(speed.parent_component, group)
        self.assertEqual(speed.depth, 1)
        self.assertTrue(speed.component_path.startswith(group.component_path))

        self.assertEqual(HmiComponentActionFact.objects.get().action_type, "setToOne")
        self.assertEqual(HmiComponentStateFact.objects.get().caption, "Running")
        self.assertEqual(HmiComponentParameterFact.objects.get().name, "#1")
        self.assertEqual(HmiGlobalObjectLinkFact.objects.get().reference, "Global Objects/Pump")
        self.assertEqual(HmiVbaLinkFact.objects.get().name, "exposeToVba")
        self.assertTrue(HmiTagReferenceFact.objects.filter(source_kind="action", base_tag="Pump01").exists())


def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]
