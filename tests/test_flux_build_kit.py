from __future__ import annotations

import json
from pathlib import Path

import pytest

from flux_build.kit import (
    KitError,
    KitInstance,
    build_default_hello_world_kit_package,
    default_hello_world_kit_instances,
    expand_kit_markers,
    write_hello_world_kit_package,
)
from flux_deep.openplc import OpenPlcV3Toolchain
from flux_deep.openplc_editor import OpenPlcEditorToolchain
from flux_deep.plc.plickir import lift_rockwell_project, write_plcopen_ld_project
from flux_mine.plc.l5k import parse_l5k_text
from flux_mine.plc.l5x import parse_l5x_text


def test_kit_expands_fx_markers_token_aware() -> None:
    instance = KitInstance(
        name="foo_bar",
        devices={"device_01": "hello_plc"},
        tags={"hello": "foo_bar"},
        pars=("foo", "bar"),
        lbl="foo_bar_inline",
    )

    assert expand_kit_markers("[fx_device_01]fx_tag_hello", instance) == "[hello_plc]foo_bar"
    assert expand_kit_markers("foo_fx_par_0_bar", instance) == "foo_foo_bar"
    assert expand_kit_markers("baz_fx_par_1", instance) == "baz_bar"
    assert expand_kit_markers("fx_par_0_TON", instance) == "foo_TON"


def test_kit_rejects_ambiguous_expansion_mode() -> None:
    with pytest.raises(KitError, match="exactly one"):
        KitInstance(
            name="bad",
            devices={"device_01": "hello_plc"},
            tags={"hello": "hello_world"},
            pars=("hello", "world"),
            routine="hello_world_cycle",
            lbl="hello_world_inline",
        )


def test_hello_world_kit_generates_three_plc_instances_and_displays() -> None:
    result = build_default_hello_world_kit_package()
    project = parse_l5k_text(result.l5k_text, source_path="hello_world_kit_generated.L5K")
    l5x_project = parse_l5x_text(result.l5x_bytes.decode("utf-8"), source_path="hello_world_kit_generated.L5X")

    assert result.plc_project.controllers[0].programs[0].routines[0].rungs[0].text == "JSR(hello_world_cycle,0);"
    assert l5x_project.controllers[0].programs[0].routines[0].rungs[0].text == "JSR(hello_world_cycle,0);"

    controller = project.controller_named("hello_world_kit")
    assert controller is not None
    program = controller.program_named("MainProgram")
    assert program is not None
    assert program.main_routine_name == "MainRoutine"
    assert {tag.name for tag in program.tags} == {
        "hello",
        "hello_latch",
        "hello_TON",
        "world",
        "world_TON",
        "hello_world",
        "foo",
        "foo_latch",
        "foo_TON",
        "bar",
        "bar_TON",
        "foo_bar",
        "baz",
        "baz_latch",
        "baz_TON",
        "bob",
        "bob_TON",
        "baz_bob",
    }

    routines = {routine.name: routine for routine in program.routines}
    assert set(routines) == {"MainRoutine", "hello_world_cycle"}
    assert routines["MainRoutine"].rungs[0].text == "JSR(hello_world_cycle,0)"
    assert routines["MainRoutine"].rungs[1].text == "XIO(foo_latch)TON(foo_TON,?,?)"
    assert routines["MainRoutine"].rungs[5].text == "[XIO(foo_latch) COP(foo,foo_bar,1) ,XIC(foo_latch) COP(bar,foo_bar,1) ]"
    assert routines["MainRoutine"].rungs[6].text == "XIO(baz_latch)TON(baz_TON,?,?)"
    assert routines["MainRoutine"].rungs[10].text == "[XIO(baz_latch) COP(baz,baz_bob,1) ,XIC(baz_latch) COP(bob,baz_bob,1) ]"
    assert routines["hello_world_cycle"].rungs[0].text == "XIO(hello_latch)TON(hello_TON,?,?)"
    assert routines["hello_world_cycle"].rungs[4].text == (
        "[XIO(hello_latch) COP(hello,hello_world,1) ,XIC(hello_latch) COP(world,hello_world,1) ]"
    )

    children = result.perspective_view["root"]["children"]
    assert [child["meta"]["name"] for child in children] == [
        "hello_world_label",
        "foo_bar_label",
        "baz_bob_label",
    ]
    assert [
        child["propConfig"]["props.text"]["binding"]["config"]["tagPath"] for child in children
    ] == ["[hello_plc]hello_world", "[hello_plc]foo_bar", "[hello_plc]baz_bob"]
    assert [child["position"]["y"] for child in children] == [24, 94, 164]

    assert result.vision_screen["schema"] == "flux.build.kit.vision_destination.v1"
    assert [obj["tagPath"] for obj in result.vision_screen["objects"]] == [
        "[hello_plc]hello_world",
        "[hello_plc]foo_bar",
        "[hello_plc]baz_bob",
    ]
    assert result.manifest["kit"] == "hello_world_display"
    assert [instance["name"] for instance in result.manifest["instances"]] == [
        instance.name for instance in default_hello_world_kit_instances()
    ]


def test_hello_world_kit_writes_package_files(tmp_path: Path) -> None:
    result = build_default_hello_world_kit_package()

    paths = write_hello_world_kit_package(result, tmp_path)

    assert paths["l5k"].name == "hello_world_kit_generated.L5K"
    assert paths["l5x"].name == "hello_world_kit_generated.L5X"
    assert paths["manifest"].name == "kit_manifest.json"
    assert json.loads(paths["perspective_view"].read_text(encoding="utf-8"))["root"]["type"] == "ia.container.coord"
    assert json.loads(paths["vision_screen"].read_text(encoding="utf-8"))["objects"][1]["name"] == "foo_bar_label"
    parse_l5k_text(paths["l5k"].read_text(encoding="utf-8"), source_path=str(paths["l5k"]))
    parse_l5x_text(paths["l5x"].read_text(encoding="utf-8"), source_path=str(paths["l5x"]))


def test_hello_world_kit_lifts_to_plickir_from_primitives(tmp_path: Path) -> None:
    result = build_default_hello_world_kit_package()

    ir = lift_rockwell_project(result.plc_project)
    plc_xml = write_plcopen_ld_project(ir, tmp_path / "editor-project")

    assert ir.diagnostics == ()
    assert plc_xml.name == "plc.xml"
    plc_text = plc_xml.read_text(encoding="utf-8")
    assert "hello_TON" in plc_text
    assert "foo_TON" in plc_text
    assert "baz_TON" in plc_text
    assert "hello_world" in plc_text
    assert "foo_bar" in plc_text
    assert "baz_bob" in plc_text


def test_openplc_certifies_hello_world_kit_from_primitives(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    editor = OpenPlcEditorToolchain.from_env()
    if editor is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_EDITOR_ROOT to a local OpenPLC_Editor checkout")
    openplc = OpenPlcV3Toolchain.from_env()
    if openplc is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_ROOT to a local OpenPLC_v3 checkout with built iec2c")

    result = build_default_hello_world_kit_package()
    ir = lift_rockwell_project(result.plc_project)
    plc_xml = write_plcopen_ld_project(ir, tmp_path / "editor-project")
    generated = editor.generate_st(plc_xml)
    generated_st = tmp_path / "hello_world_kit_generated.st"
    generated_st.write_text(generated.st_text, encoding="utf-8")

    compiled = openplc.compile_st(generated_st, output_dir=tmp_path / "compiled")
    harness = openplc.compile_and_run_harness(compiled, hello_world_kit_harness_source())

    assert generated.errors == ()
    assert generated.warnings == ()
    by_tick = {
        int(tick): {"hello_world": hello_world, "foo_bar": foo_bar, "baz_bob": baz_bob}
        for tick, hello_world, foo_bar, baz_bob in (line.split(",") for line in harness.stdout.strip().splitlines())
    }
    assert by_tick[0] == {"hello_world": "hello", "foo_bar": "foo", "baz_bob": "baz"}
    assert by_tick[11] == {"hello_world": "world", "foo_bar": "bar", "baz_bob": "bob"}
    assert by_tick[22] == {"hello_world": "hello", "foo_bar": "foo", "baz_bob": "baz"}


def hello_world_kit_harness_source() -> str:
    return r'''
#include <stdio.h>
#include "iec_std_lib.h"
#include "accessor.h"
#include "POUS.h"
#include "Config0.h"

TIME __CURRENT_TIME = {0, 0};
BOOL __DEBUG = 0;

int connect_to_tcp_server(uint8_t *ip_address, uint16_t port, int method) {
  (void)ip_address;
  (void)port;
  (void)method;
  return -1;
}

int send_tcp_message(uint8_t *msg, size_t msg_size, int socket_id) {
  (void)msg;
  (void)msg_size;
  (void)socket_id;
  return -1;
}

int receive_tcp_message(uint8_t *msg_buffer, size_t buffer_size, int socket_id) {
  (void)msg_buffer;
  (void)buffer_size;
  (void)socket_id;
  return -1;
}

void config_init__(void);
void config_run__(unsigned long tick);
extern MAINPROGRAM RES0__MAINPROGRAMINSTANCE;

static void set_time_ms(long milliseconds) {
  __CURRENT_TIME.tv_sec = milliseconds / 1000;
  __CURRENT_TIME.tv_nsec = (milliseconds % 1000) * 1000000;
}

static void print_sample(unsigned long tick) {
  STRING hello_world = __GET_VAR(RES0__MAINPROGRAMINSTANCE.HELLO_WORLD,);
  STRING foo_bar = __GET_VAR(RES0__MAINPROGRAMINSTANCE.FOO_BAR,);
  STRING baz_bob = __GET_VAR(RES0__MAINPROGRAMINSTANCE.BAZ_BOB,);
  printf("%lu,%.*s,%.*s,%.*s\n",
         tick,
         (int)hello_world.len,
         hello_world.body,
         (int)foo_bar.len,
         foo_bar.body,
         (int)baz_bob.len,
         baz_bob.body);
}

int main(void) {
  config_init__();
  for (unsigned long tick = 0; tick <= 24; tick++) {
    set_time_ms((long)tick * 100);
    config_run__(tick);
    print_sample(tick);
  }
  return 0;
}
'''
