from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

L5X_RELATIVE_PATH = Path("hello_world.l5x")
OPENPLC_ST_RELATIVE_PATH = Path("openplc") / "hello_world.st"
MANIFEST_RELATIVE_PATH = Path("manifest.json")
README_RELATIVE_PATH = Path("README.md")


@dataclass(frozen=True)
class DeepFile:
    relative_path: Path
    content: str


@dataclass(frozen=True)
class DeepWorkspace:
    name: str
    files: tuple[DeepFile, ...]

    def write_to(self, output_dir: str | Path, *, overwrite: bool = False) -> list[Path]:
        root = Path(output_dir)
        written: list[Path] = []
        for file in self.files:
            target = root / file.relative_path
            if target.exists() and not overwrite:
                raise FileExistsError(f"Refusing to overwrite existing Flux.Deep file: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content, encoding="utf-8")
            written.append(target)
        return written


def render_hello_world_l5x() -> str:
    return dedent(
        """\
        <?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <RSLogix5000Content
          SchemaRevision="1.0"
          SoftwareRevision="35.00"
          TargetName="hello_world"
          TargetType="Controller"
          ContainsContext="true"
          Owner="Flux.Deep"
          ExportOptions="References NoRawData L5KData DecoratedData Context">
          <Controller
            Use="Target"
            Name="hello_world"
            ProcessorType="1756-L83E"
            MajorRev="35"
            MinorRev="00"
            TimeSlice="20"
            ShareUnusedTimeSlice="1">
            <Tags>
              <Tag
                Name="CycleCount"
                TagType="Base"
                DataType="DINT"
                Radix="Decimal"
                Constant="false"
                ExternalAccess="Read/Write">
                <Data Format="L5K"><![CDATA[0]]></Data>
                <Data Format="Decorated">
                  <DataValue DataType="DINT" Radix="Decimal" Value="0" />
                </Data>
              </Tag>
              <Tag
                Name="CycleTimer"
                TagType="Base"
                DataType="TIMER"
                Constant="false"
                ExternalAccess="Read/Write" />
              <Tag
                Name="DisplayText"
                TagType="Base"
                DataType="STRING"
                Constant="false"
                ExternalAccess="Read/Write">
                <Data Format="L5K"><![CDATA[[5,'world']]]></Data>
                <Data Format="Decorated">
                  <Structure DataType="STRING">
                    <DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="5" />
                    <DataValueMember Name="DATA" DataType="SINT" Radix="ASCII" Value="'world'" />
                  </Structure>
                </Data>
              </Tag>
              <Tag
                Name="HelloText"
                TagType="Base"
                DataType="STRING"
                Constant="false"
                ExternalAccess="Read/Write">
                <Data Format="L5K"><![CDATA[[5,'hello']]]></Data>
                <Data Format="Decorated">
                  <Structure DataType="STRING">
                    <DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="5" />
                    <DataValueMember Name="DATA" DataType="SINT" Radix="ASCII" Value="'hello'" />
                  </Structure>
                </Data>
              </Tag>
              <Tag
                Name="WorldText"
                TagType="Base"
                DataType="STRING"
                Constant="false"
                ExternalAccess="Read/Write">
                <Data Format="L5K"><![CDATA[[5,'world']]]></Data>
                <Data Format="Decorated">
                  <Structure DataType="STRING">
                    <DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="5" />
                    <DataValueMember Name="DATA" DataType="SINT" Radix="ASCII" Value="'world'" />
                  </Structure>
                </Data>
              </Tag>
            </Tags>
            <Programs>
              <Program
                Name="MainProgram"
                TestEdits="false"
                MainRoutineName="MainRoutine"
                Disabled="false">
                <Routines>
                  <Routine Name="MainRoutine" Type="RLL">
                    <RLLContent>
                      <Rung Number="0" Type="N">
                        <Comment><![CDATA[Run a one second self-resetting timer.]]></Comment>
                        <Text><![CDATA[XIO(CycleTimer.DN)TON(CycleTimer,?,1000,0);]]></Text>
                      </Rung>
                      <Rung Number="1" Type="N">
                        <Comment><![CDATA[Count each completed one second cycle.]]></Comment>
                        <Text><![CDATA[XIC(CycleTimer.DN)ADD(CycleCount,1,CycleCount)RES(CycleTimer);]]></Text>
                      </Rung>
                      <Rung Number="2" Type="N">
                        <Comment><![CDATA[Odd cycles publish hello.]]></Comment>
                        <Text><![CDATA[XIC(CycleCount.0)COP(HelloText,DisplayText,1);]]></Text>
                      </Rung>
                      <Rung Number="3" Type="N">
                        <Comment><![CDATA[Even cycles publish world.]]></Comment>
                        <Text><![CDATA[XIO(CycleCount.0)COP(WorldText,DisplayText,1);]]></Text>
                      </Rung>
                    </RLLContent>
                  </Routine>
                </Routines>
              </Program>
            </Programs>
            <Tasks>
              <Task
                Name="MainTask"
                Type="CONTINUOUS"
                Watchdog="500"
                DisableUpdateOutputs="false"
                InhibitTask="false">
                <ScheduledPrograms>
                  <ScheduledProgram Name="MainProgram" />
                </ScheduledPrograms>
              </Task>
            </Tasks>
          </Controller>
        </RSLogix5000Content>
        """
    )


def render_openplc_hello_world_st() -> str:
    return dedent(
        """\
        PROGRAM hello_world
        VAR
          cycle_timer : TON;
          timer_enable : BOOL := TRUE;
          cycle_count : DINT := 0;
          display_text : STRING := 'world';
        END_VAR

        cycle_timer(IN := timer_enable, PT := T#1s);

        IF cycle_timer.Q THEN
          timer_enable := FALSE;
          cycle_count := cycle_count + 1;

          IF (cycle_count MOD 2) = 1 THEN
            display_text := 'hello';
          ELSE
            display_text := 'world';
          END_IF;
        ELSE
          timer_enable := TRUE;
        END_IF;
        END_PROGRAM

        CONFIGURATION Config0
        RESOURCE Res0 ON PLC
        TASK Main(INTERVAL := T#50ms, PRIORITY := 0);
        PROGRAM MainInstance WITH Main : hello_world;
        END_RESOURCE
        END_CONFIGURATION
        """
    )


def render_hello_world_manifest() -> str:
    manifest = {
        "schema": "flux.deep.workspace.v1",
        "name": "hello_world",
        "owner": "Flux.Deep",
        "isolation": "top-level core package; no Django or Ignition service coupling",
        "runtime_backend": "openplc",
        "source_format": "logix_l5x",
        "source_entrypoint": L5X_RELATIVE_PATH.as_posix(),
        "openplc_entrypoint": OPENPLC_ST_RELATIVE_PATH.as_posix(),
        "cycle_seconds": 1,
        "observed_tags": [
            {"name": "DisplayText", "data_type": "STRING", "values": ["hello", "world"]},
            {"name": "CycleCount", "data_type": "DINT"},
        ],
        "status": "seed_workspace",
        "notes": [
            "The L5X file records the Logix ladder source intent.",
            "OpenPLC does not run L5X directly; the ST file is the first executable target.",
        ],
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def render_hello_world_readme() -> str:
    return dedent(
        """\
        # Flux.Deep Hello World

        This is the first isolated Flux.Deep PLC emulation workspace.

        Files:

        - `hello_world.l5x`: Logix ladder source seed. It runs a one second timer,
          increments `CycleCount`, and copies `hello` or `world` into `DisplayText`.
        - `openplc/hello_world.st`: OpenPLC Structured Text target with the same scan
          behavior. This is the near-term executable artifact for OpenPLC.
        - `manifest.json`: Flux.Deep workspace metadata for future automation.

        Local regeneration:

        ```bash
        flux deep init-hello-world --output deep/examples/hello_world --force
        ```

        Architecture note: OpenPLC is the backend runtime, but it does not ingest
        Rockwell L5X directly. Flux.Deep should grow a translator from the Logix source
        model into OpenPLC-compatible IEC 61131-3 artifacts instead of coupling this
        work to Django, Ignition, or FieldAgent.
        """
    )


def hello_world_workspace() -> DeepWorkspace:
    return DeepWorkspace(
        name="hello_world",
        files=(
            DeepFile(L5X_RELATIVE_PATH, render_hello_world_l5x()),
            DeepFile(OPENPLC_ST_RELATIVE_PATH, render_openplc_hello_world_st()),
            DeepFile(MANIFEST_RELATIVE_PATH, render_hello_world_manifest()),
            DeepFile(README_RELATIVE_PATH, render_hello_world_readme()),
        ),
    )


def write_hello_world_workspace(output_dir: str | Path, *, overwrite: bool = False) -> list[Path]:
    return hello_world_workspace().write_to(output_dir, overwrite=overwrite)
