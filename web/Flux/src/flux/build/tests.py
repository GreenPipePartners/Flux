from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from flux_build.targets.logix_l5x import build_logix_l5x
from flux_mine.plc.l5k import parse_l5k_text
from flux_mine.plc.l5x import parse_l5x_file, parse_l5x_text
from flux_mine.plc.models import PlcProject, PlcRoutine, PlcRung, PlcTag, parse_rll_instructions

from flux.cell.models import Cell, Point, Source, Visual
from flux.mine.models import HmiTagReferenceFact, MineRun
from flux.mine.services import mine_factorytalk_sqlite_export

from flux.mine.models import HmiComponentFact

from .models import BuildArtifact, BuildRun, HmiMapSelection
from .services import default_hmi_demo_sqlite_path, seed_hmi_demo_build_sample


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

            call_command(
                "flux_build_ignition_tags", mine_run.id, "--output", str(output), stdout=StringIO()
            )

            payload = json.loads(output.read_text(encoding="utf-8"))

        build_run = BuildRun.objects.get()
        self.assertEqual(build_run.status, BuildRun.Status.COMPLETE)
        self.assertEqual(BuildArtifact.objects.get().kind, "ignition_provider_json")
        self.assertEqual(payload["tagType"], "Provider")
        self.assertIn("_types_", {tag["name"] for tag in payload["tags"]})
        self.assertEqual(
            build_run.output_bytes,
            len(json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")) + 1,
        )

    def test_flux_build_hmi_map_writes_symbolic_map_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "FactoryTalk"
            output_dir = root / "hmi-map"
            (source_root / "Screens").mkdir(parents=True)
            (source_root / "Screens" / "Overview.xml").write_text(
                """
                <gfx>
                  <displaySettings width="800" height="600" />
                  <numericDisplay name="Pressure" left="10" top="20" width="100" height="30" tag="{[PLC]PT001}" />
                  <button name="Start" left="30" top="70" width="80" height="24" />
                </gfx>
                """.strip(),
                encoding="utf-8",
            )
            call_command(
                "flux_mine_source",
                str(source_root),
                "--source-type",
                "factorytalk",
                stdout=StringIO(),
            )
            mine_run = MineRun.objects.get()

            call_command(
                "flux_build_hmi_map",
                mine_run.id,
                "--output-dir",
                str(output_dir),
                stdout=StringIO(),
            )
            payload = json.loads((output_dir / "hmi_map.json").read_text(encoding="utf-8"))

        build_run = BuildRun.objects.get()
        self.assertEqual(build_run.status, BuildRun.Status.COMPLETE)
        self.assertEqual(build_run.target, BuildRun.Target.HMI_SYMBOLIC_MAP)
        self.assertEqual(build_run.summary["component_count"], 1)
        self.assertEqual(
            {artifact.kind for artifact in BuildArtifact.objects.all()},
            {"hmi_symbolic_map_json", "hmi_symbolic_map_svg"},
        )
        symbols = {
            component["symbol"] for component in payload["project"]["screens"][0]["components"]
        }
        self.assertEqual(symbols, {"N"})

    def test_flux_build_logix_l5x_writes_parse_back_artifact_from_hello_world(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = write_hello_world_foobar_source(root)
            output = root / "artifacts" / "hello_world_generated.L5X"

            call_command("flux_mine_source", str(source), stdout=StringIO())
            mine_run = MineRun.objects.get()
            call_command("flux_build_logix_l5x", mine_run.id, "--output", str(output), stdout=StringIO())

            generated_project = parse_l5x_text(output.read_text(encoding="utf-8"), source_path=str(output))
            generated_text = output.read_text(encoding="utf-8")

        build_run = BuildRun.objects.get()
        self.assertEqual(build_run.status, BuildRun.Status.COMPLETE)
        self.assertEqual(build_run.target, BuildRun.Target.LOGIX_L5X)
        self.assertEqual(BuildArtifact.objects.get().kind, "logix_l5x")
        self.assertEqual(build_run.summary["controller_count"], 1)
        self.assertEqual(build_run.summary["program_count"], 1)
        self.assertEqual(build_run.summary["task_count"], 1)
        self.assertEqual(build_run.summary["routine_count"], 2)
        self.assertEqual(build_run.summary["rung_count"], 11)
        self.assertEqual(build_run.summary["instruction_count"], 25)
        self.assertEqual(build_run.summary["tag_reference_count"], 28)
        self.assertTrue(build_run.summary["round_trip"]["counts_match"])

        controller = generated_project.controller_named("hello_world")
        self.assertIsNotNone(controller)
        assert controller is not None
        program = controller.program_named("MainProgram")
        self.assertIsNotNone(program)
        assert program is not None
        self.assertEqual(program.main_routine_name, "MainRoutine")
        self.assertEqual(len(program.tags), 12)
        self.assertEqual(controller.task_named("MainTask").scheduled_programs, ("MainProgram",))
        routines = {routine.name: routine for routine in program.routines}
        self.assertEqual(set(routines), {"MainRoutine", "foobar"})
        routine = routines["MainRoutine"]
        self.assertEqual(len(routine.rungs), 6)
        instructions = [instruction for rung in routine.rungs for instruction in rung.instructions]
        references = [reference for instruction in instructions for reference in instruction.tag_references]
        self.assertEqual(len(instructions), 13)
        self.assertEqual(len(references), 14)
        self.assertEqual(routine.rungs[4].text, "[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ];")
        self.assertEqual(routine.rungs[5].text, "JSR(foobar,0);")
        foobar = routines["foobar"]
        self.assertEqual(len(foobar.rungs), 5)
        self.assertEqual(foobar.rungs[4].text, "[XIO(bar_latch) COP(foo,foo_bar,1) ,XIC(bar_latch) COP(bar,foo_bar,1) ];")
        foobar_instructions = [instruction for rung in foobar.rungs for instruction in rung.instructions]
        foobar_references = [reference for instruction in foobar_instructions for reference in instruction.tag_references]
        self.assertEqual(len(foobar_instructions), 12)
        self.assertEqual(len(foobar_references), 14)
        self.assertIn('<Structure DataType="TIMER">', generated_text)
        self.assertIn('<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="1000"', generated_text)
        self.assertIn('<DataValue DataType="BOOL" Radix="Decimal" Value="0"', generated_text)
        self.assertIn('<Routine Name="foobar" Type="RLL">', generated_text)
        self.assertIn('JSR(foobar,0);', generated_text)
        self.assertIn('XIO(bar_latch)TON(foo_TON,?,?);', generated_text)
        self.assertIn("<Data Format=\"String\" Length=\"3\">'foo'</Data>", generated_text)
        self.assertIn("<Data Format=\"String\" Length=\"3\">'bar'</Data>", generated_text)

    def test_flux_build_logix_l5k_writes_parse_back_artifact_from_hello_world(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = write_hello_world_foobar_source(root)
            output = root / "artifacts" / "hello_world_generated.L5K"

            call_command("flux_mine_source", str(source), stdout=StringIO())
            mine_run = MineRun.objects.get()
            call_command("flux_build_logix_l5k", mine_run.id, "--output", str(output), stdout=StringIO())

            generated_project = parse_l5k_text(output.read_text(encoding="utf-8"), source_path=str(output))

        build_run = BuildRun.objects.get()
        self.assertEqual(build_run.status, BuildRun.Status.COMPLETE)
        self.assertEqual(build_run.target, BuildRun.Target.LOGIX_L5K)
        self.assertEqual(BuildArtifact.objects.get().kind, "logix_l5k")
        self.assertEqual(build_run.summary["controller_count"], 1)
        self.assertEqual(build_run.summary["program_count"], 1)
        self.assertEqual(build_run.summary["task_count"], 1)
        self.assertEqual(build_run.summary["routine_count"], 2)
        self.assertEqual(build_run.summary["rung_count"], 11)
        self.assertEqual(build_run.summary["instruction_count"], 25)
        self.assertEqual(build_run.summary["tag_reference_count"], 28)
        self.assertTrue(build_run.summary["round_trip"]["counts_match"])

        controller = generated_project.controller_named("hello_world")
        self.assertIsNotNone(controller)
        assert controller is not None
        program = controller.program_named("MainProgram")
        self.assertIsNotNone(program)
        assert program is not None
        self.assertEqual(program.main_routine_name, "MainRoutine")
        self.assertEqual(len(program.tags), 12)
        task = controller.task_named("MainTask")
        self.assertIsNotNone(task)
        assert task is not None
        self.assertEqual(task.scheduled_programs, ("MainProgram",))
        routines = {routine.name: routine for routine in program.routines}
        self.assertEqual(set(routines), {"MainRoutine", "foobar"})
        routine = routines["MainRoutine"]
        instructions = [instruction for rung in routine.rungs for instruction in rung.instructions]
        references = [reference for instruction in instructions for reference in instruction.tag_references]
        self.assertEqual(len(instructions), 13)
        self.assertEqual(len(references), 14)
        self.assertEqual(
            routine.rungs[4].text,
            "[XIO(world_latch) COP(hello,hello_world,1) ,XIC(world_latch) COP(world,hello_world,1) ]",
        )
        self.assertEqual(routine.rungs[5].text, "JSR(foobar,0)")
        foobar = routines["foobar"]
        self.assertEqual(foobar.rungs[4].text, "[XIO(bar_latch) COP(foo,foo_bar,1) ,XIC(bar_latch) COP(bar,foo_bar,1) ]")
        foobar_instructions = [instruction for rung in foobar.rungs for instruction in rung.instructions]
        foobar_references = [reference for instruction in foobar_instructions for reference in instruction.tag_references]
        self.assertEqual(len(foobar_instructions), 12)
        self.assertEqual(len(foobar_references), 14)

    def test_build_hmi_map_webform_uses_selected_components(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "FactoryTalk"
            output_dir = root / "hmi-map"
            (source_root / "Screens").mkdir(parents=True)
            (source_root / "Screens" / "Overview.xml").write_text(
                """
                <gfx>
                  <displaySettings width="800" height="600" />
                  <numericDisplay name="Pressure" left="10" top="20" width="100" height="30" tag="{[PLC]PT001}" />
                  <button name="Start" left="30" top="70" width="80" height="24" />
                </gfx>
                """.strip(),
                encoding="utf-8",
            )
            call_command(
                "flux_mine_source",
                str(source_root),
                "--source-type",
                "factorytalk",
                stdout=StringIO(),
            )
            mine_run = MineRun.objects.get()
            selected = HmiComponentFact.objects.get(name="Pressure")

            response = self.client.post(
                "/build/hmi-map/build/",
                {
                    "mine_run_id": mine_run.id,
                    "output_dir": str(output_dir),
                    "component_id": [selected.id],
                },
                follow=True,
            )
            payload = json.loads((output_dir / "hmi_map.json").read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(HmiMapSelection.objects.get().component, selected)
        self.assertEqual(BuildRun.objects.get().summary["component_count"], 1)
        self.assertEqual(payload["project"]["screens"][0]["components"][0]["name"], "Pressure")

    def test_build_page_shows_tagged_components_on_clickable_screen_map_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "FactoryTalk"
            (source_root / "Screens").mkdir(parents=True)
            (source_root / "Screens" / "Overview.xml").write_text(
                """
                <gfx>
                  <displaySettings width="800" height="600" />
                  <numericDisplay name="Pressure" left="10" top="20" width="100" height="30" tag="{[PLC]PT001}" />
                  <rectangle name="StaticPanel" left="30" top="70" width="80" height="24" />
                </gfx>
                """.strip(),
                encoding="utf-8",
            )
            call_command(
                "flux_mine_source",
                str(source_root),
                "--source-type",
                "factorytalk",
                stdout=StringIO(),
            )

            response = self.client.get("/build/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Physical Screen Map")
        self.assertContains(response, "data-build-map-selector")
        self.assertContains(response, "data-build-map-node")
        self.assertContains(response, "data-build-component-checkbox")
        self.assertContains(response, "Pressure")
        self.assertContains(response, "[PLC]PT001")
        self.assertNotContains(response, "StaticPanel")
        self.assertNotContains(response, "No tags")

    def test_build_hmi_map_webform_creates_cell_draft_from_selected_components(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "FactoryTalk"
            (source_root / "Screens").mkdir(parents=True)
            (source_root / "Screens" / "Overview.xml").write_text(
                """
                <gfx>
                  <displaySettings width="800" height="600" />
                  <numericDisplay name="Pressure" left="10" top="20" width="100" height="30" tag="{[PLC]PT001}" />
                  <button name="Start" left="30" top="70" width="80" height="24">
                    <action type="setToOne" tag="{[PLC]StartCmd}" />
                  </button>
                </gfx>
                """.strip(),
                encoding="utf-8",
            )
            call_command(
                "flux_mine_source",
                str(source_root),
                "--source-type",
                "factorytalk",
                stdout=StringIO(),
            )
            mine_run = MineRun.objects.get()
            selected_ids = list(HmiComponentFact.objects.values_list("id", flat=True))

            response = self.client.post(
                "/build/hmi-map/build/",
                {
                    "action": "create_cell_draft",
                    "mine_run_id": mine_run.id,
                    "component_id": selected_ids,
                    "cell_bundle_key": "test-hmi",
                    "cell_bundle_name": "Test HMI",
                    "cell_slug": "pump-01",
                    "cell_name": "Pump 01",
                    "cell_group": "Pad A",
                    "cell_kind": "Pump",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created cell draft Pump 01")
        cell = Cell.objects.get(slug="pump-01")
        self.assertEqual(cell.name, "Pump 01")
        self.assertEqual(cell.group, "Pad A")
        self.assertEqual(cell.kind, "Pump")
        self.assertEqual(Source.objects.filter(cell=cell).count(), 2)
        self.assertEqual(Visual.objects.filter(cell=cell).count(), 2)
        pressure = Point.objects.get(cell=cell, full_path="[PLC]PT001")
        self.assertTrue(pressure.include_live)
        self.assertTrue(pressure.include_trace)
        command = Point.objects.get(cell=cell, full_path="[PLC]StartCmd")
        self.assertFalse(command.include_live)
        self.assertFalse(command.include_trace)

    @unittest.skipUnless(
        default_hmi_demo_sqlite_path().exists(), "HMI demo SQLite sample is not available"
    )
    def test_hmi_demo_sqlite_imports_verified_recovery_facts(self) -> None:
        run = mine_factorytalk_sqlite_export(
            default_hmi_demo_sqlite_path(),
            label="HMI demo test sample",
            max_display_screens=3,
        )

        self.assertEqual(run.status, MineRun.Status.COMPLETE)
        self.assertEqual(run.summary["sqlite_counts"]["screens"], 119)
        self.assertEqual(run.summary["sqlite_counts"]["components"], 22559)
        self.assertEqual(run.summary["screen_count"], 3)
        self.assertEqual(run.summary["component_count"], 205)
        self.assertGreaterEqual(run.summary["tag_reference_count"], 100)
        self.assertEqual(run.hmi_screens.count(), 3)
        self.assertEqual(HmiComponentFact.objects.filter(run=run).count(), 205)
        self.assertGreater(HmiTagReferenceFact.objects.filter(run=run).count(), 100)

    @unittest.skipUnless(
        default_hmi_demo_sqlite_path().exists(), "HMI demo SQLite sample is not available"
    )
    def test_seed_hmi_demo_build_sample_creates_symbolic_map_and_ui_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            build_run = seed_hmi_demo_build_sample(
                sqlite_path=default_hmi_demo_sqlite_path(),
                max_display_screens=3,
                output_dir=Path(temp_dir) / "build-sample",
            )

            response = self.client.get("/build/")

        self.assertEqual(build_run.status, BuildRun.Status.COMPLETE)
        self.assertEqual(build_run.summary["screen_count"], 2)
        self.assertEqual(build_run.summary["component_count"], 58)
        self.assertEqual(BuildArtifact.objects.filter(run=build_run).count(), 3)
        self.assertContains(response, "Recovered HMI Demo Shape")
        self.assertContains(response, "Demo HMI SQLite sample")
        self.assertContains(response, "A1 SERVER STATUS.xml")
        self.assertContains(response, "Physical Screen Map")
        self.assertContains(response, "data-build-map-node")
        self.assertContains(response, "numericDisplay")
        self.assertContains(response, "Latest Symbolic Map Build")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def write_hello_world_foobar_source(root: Path) -> Path:
    source = root / "hello_world_foobar.source.L5X"
    source.write_bytes(build_logix_l5x(hello_world_with_foobar_project()))
    return source


def hello_world_with_foobar_project() -> PlcProject:
    project = parse_l5x_file(repo_root() / "logix_samples" / "hello_world.L5X")
    controller = project.controllers[0]
    program = controller.programs[0]
    tag_by_name = {tag.name: tag for tag in program.tags}
    foobar_tags = (
        renamed_string_tag(tag_by_name["hello"], name="foo", value="foo"),
        renamed_tag(tag_by_name["hello_TON"], name="foo_TON"),
        renamed_string_tag(tag_by_name["hello_world"], name="foo_bar", value=""),
        renamed_string_tag(tag_by_name["world"], name="bar", value="bar"),
        renamed_tag(tag_by_name["world_latch"], name="bar_latch"),
        renamed_tag(tag_by_name["world_TON"], name="bar_TON"),
    )
    expanded_program = replace(
        program,
        tags=program.tags + foobar_tags,
        routines=(main_routine_with_foobar_jsr(program.routines[0]), foobar_routine()),
    )
    expanded_controller = replace(controller, programs=(expanded_program,))
    return replace(project, controllers=(expanded_controller,))


def main_routine_with_foobar_jsr(routine: PlcRoutine) -> PlcRoutine:
    jsr_text = "JSR(foobar,0);"
    jsr_rung = PlcRung(
        number=max((rung.number for rung in routine.rungs), default=-1) + 1,
        rung_type="N",
        text=jsr_text,
        instructions=parse_rll_instructions(jsr_text),
        raw={"Number": str(len(routine.rungs)), "Type": "N"},
    )
    return replace(routine, rungs=routine.rungs + (jsr_rung,))


def foobar_routine() -> PlcRoutine:
    rung_texts = (
        "XIO(bar_latch)TON(foo_TON,?,?);",
        "XIC(foo_TON.DN)OTL(bar_latch);",
        "XIC(bar_latch)TON(bar_TON,?,?);",
        "XIC(bar_TON.DN)OTU(bar_latch);",
        "[XIO(bar_latch) COP(foo,foo_bar,1) ,XIC(bar_latch) COP(bar,foo_bar,1) ];",
    )
    return PlcRoutine(
        name="foobar",
        routine_type="RLL",
        rungs=tuple(
            PlcRung(
                number=number,
                rung_type="N",
                text=text,
                instructions=parse_rll_instructions(text),
                raw={"Number": str(number), "Type": "N"},
            )
            for number, text in enumerate(rung_texts)
        ),
        raw={"Name": "foobar", "Type": "RLL"},
    )


def renamed_tag(tag: PlcTag, *, name: str) -> PlcTag:
    raw = deepcopy(tag.raw)
    raw["Name"] = name
    return replace(tag, name=name, raw=raw)


def renamed_string_tag(tag: PlcTag, *, name: str, value: str) -> PlcTag:
    raw = deepcopy(tag.raw)
    raw["Name"] = name
    for payload in raw.get("data", []):
        if payload.get("format") == "L5K":
            payload["text"] = string_l5k_payload(value)
        elif payload.get("format") == "String":
            payload["text"] = f"'{value}'"
            payload.setdefault("attributes", {})["Length"] = str(len(value))
    return replace(tag, name=name, raw=raw)


def string_l5k_payload(value: str) -> str:
    return f"[{len(value)},'{value}{'$00' * (82 - len(value))}'\n\t\t]"
