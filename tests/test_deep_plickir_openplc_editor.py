from __future__ import annotations

from pathlib import Path

import pytest

from flux_deep.openplc import OpenPlcV3Toolchain
from flux_deep.openplc_editor import OpenPlcEditorToolchain
from flux_deep.plc.plickir import lift_rockwell_project, write_plcopen_ld_project
from flux_mine.plc.l5x import parse_l5x_file


def test_openplc_editor_generates_st_from_plickir_ld_project(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    editor = OpenPlcEditorToolchain.from_env()
    if editor is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_EDITOR_ROOT to a local OpenPLC_Editor checkout")

    ir = lift_rockwell_project(parse_l5x_file(repo_root() / "logix_samples" / "hello_world.L5X"))
    plc_xml = write_plcopen_ld_project(ir, tmp_path)

    result = editor.generate_st(plc_xml)

    assert result.errors == ()
    assert result.warnings == ()
    assert "PROGRAM MainProgram" in result.st_text
    assert "hello_TON(EN := TRUE, IN := NOT(world_latch), PT := T#1000ms);" in result.st_text
    assert "world_TON(EN := TRUE, IN := world_latch, PT := T#1000ms);" in result.st_text
    assert "world_latch := TRUE; (*set*)" in result.st_text
    assert "world_latch := FALSE; (*reset*)" in result.st_text
    assert "MOVE(EN := NOT(world_latch), IN := hello" in result.st_text
    assert "MOVE(EN := world_latch, IN := world" in result.st_text
    assert "hello_world := _TMP_MOVE" in result.st_text


def test_openplc_matiec_compiles_editor_generated_st_from_plickir_ld(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    editor = OpenPlcEditorToolchain.from_env()
    if editor is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_EDITOR_ROOT to a local OpenPLC_Editor checkout")
    openplc = OpenPlcV3Toolchain.from_env()
    if openplc is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_ROOT to a local OpenPLC_v3 checkout with built iec2c")

    ir = lift_rockwell_project(parse_l5x_file(repo_root() / "logix_samples" / "hello_world.L5X"))
    plc_xml = write_plcopen_ld_project(ir, tmp_path / "editor-project")
    generated = editor.generate_st(plc_xml)
    generated_st = tmp_path / "generated_plc.st"
    generated_st.write_text(generated.st_text, encoding="utf-8")

    compiled = openplc.compile_st(generated_st, output_dir=tmp_path / "compiled")

    generated_names = {path.name for path in compiled.generated_files}
    assert {"POUS.c", "POUS.h", "Config0.c", "Config0.h", "Res0.c"}.issubset(generated_names)


def test_openplc_editor_generates_st_from_hello_world_foobar_generated_l5x(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    editor = OpenPlcEditorToolchain.from_env()
    if editor is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_EDITOR_ROOT to a local OpenPLC_Editor checkout")

    ir = lift_rockwell_project(parse_l5x_file(generated_foobar_l5x()))
    plc_xml = write_plcopen_ld_project(ir, tmp_path / "editor-project")

    result = editor.generate_st(plc_xml)

    assert ir.diagnostics == ()
    assert result.errors == ()
    assert result.warnings == ()
    assert "hello_TON(EN := TRUE, IN := NOT(world_latch), PT := T#1000ms);" in result.st_text
    assert "world_TON(EN := TRUE, IN := world_latch, PT := T#1000ms);" in result.st_text
    assert "foo_TON(EN := TRUE, IN := NOT(bar_latch), PT := T#1000ms);" in result.st_text
    assert "bar_TON(EN := TRUE, IN := bar_latch, PT := T#1000ms);" in result.st_text
    assert "world_latch := TRUE; (*set*)" in result.st_text
    assert "bar_latch := TRUE; (*set*)" in result.st_text
    assert "hello_world := _TMP_MOVE" in result.st_text
    assert "foo_bar := _TMP_MOVE" in result.st_text


def test_openplc_matiec_compiles_hello_world_foobar_generated_l5x(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    editor = OpenPlcEditorToolchain.from_env()
    if editor is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_EDITOR_ROOT to a local OpenPLC_Editor checkout")
    openplc = OpenPlcV3Toolchain.from_env()
    if openplc is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_ROOT to a local OpenPLC_v3 checkout with built iec2c")

    ir = lift_rockwell_project(parse_l5x_file(generated_foobar_l5x()))
    plc_xml = write_plcopen_ld_project(ir, tmp_path / "editor-project")
    generated = editor.generate_st(plc_xml)
    generated_st = tmp_path / "hello_world_foobar_generated.st"
    generated_st.write_text(generated.st_text, encoding="utf-8")

    compiled = openplc.compile_st(generated_st, output_dir=tmp_path / "compiled")
    harness = openplc.compile_and_run_harness(compiled, hello_world_foobar_harness_source())

    generated_names = {path.name for path in compiled.generated_files}
    assert {"POUS.c", "POUS.h", "Config0.c", "Config0.h", "Res0.c"}.issubset(generated_names)
    samples = [line.split(",") for line in harness.stdout.strip().splitlines()]
    by_tick = {
        int(tick): {
            "world_latch": world_latch == "1",
            "hello_world": hello_world,
            "bar_latch": bar_latch == "1",
            "foo_bar": foo_bar,
        }
        for tick, world_latch, hello_world, bar_latch, foo_bar in samples
    }
    assert by_tick[0] == {
        "world_latch": False,
        "hello_world": "hello",
        "bar_latch": False,
        "foo_bar": "foo",
    }
    assert by_tick[11] == {
        "world_latch": True,
        "hello_world": "world",
        "bar_latch": True,
        "foo_bar": "bar",
    }
    assert by_tick[22] == {
        "world_latch": False,
        "hello_world": "hello",
        "bar_latch": False,
        "foo_bar": "foo",
    }


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def generated_foobar_l5x() -> Path:
    return repo_root() / "logix_samples" / "generated" / "hello_world_foobar_generated.L5X"


def hello_world_foobar_harness_source() -> str:
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
  printf("%lu,%d,%.*s,%d,%.*s\n",
         tick,
         (int)__GET_VAR(RES0__MAINPROGRAMINSTANCE.WORLD_LATCH,),
         (int)hello_world.len,
         hello_world.body,
         (int)__GET_VAR(RES0__MAINPROGRAMINSTANCE.BAR_LATCH,),
         (int)foo_bar.len,
         foo_bar.body);
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
