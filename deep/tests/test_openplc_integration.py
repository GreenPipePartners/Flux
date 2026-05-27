from __future__ import annotations

from pathlib import Path

import pytest

from flux_deep.hello_world import OPENPLC_ST_RELATIVE_PATH
from flux_deep.openplc import OpenPlcV3Toolchain


def test_openplc_v3_matiec_compiles_hello_world_st(tmp_path: Path) -> None:
    toolchain = OpenPlcV3Toolchain.from_env()
    if toolchain is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_ROOT to a local OpenPLC_v3 checkout with built iec2c")

    source = Path(__file__).resolve().parents[1] / "examples" / "hello_world" / OPENPLC_ST_RELATIVE_PATH

    result = toolchain.compile_st(source, output_dir=tmp_path)

    generated_names = {path.name for path in result.generated_files}
    assert {"POUS.c", "POUS.h", "Config0.c", "Config0.h", "Res0.c"}.issubset(generated_names)
    assert "MAINPROGRAM_body__" in (tmp_path / "POUS.c").read_text(encoding="utf-8", errors="ignore")


def test_openplc_v3_harness_observes_hello_world_cycle(tmp_path: Path) -> None:
    toolchain = OpenPlcV3Toolchain.from_env()
    if toolchain is None:
        pytest.skip("Set FLUX_DEEP_OPENPLC_ROOT to a local OpenPLC_v3 checkout with built iec2c")

    source = Path(__file__).resolve().parents[1] / "examples" / "hello_world" / OPENPLC_ST_RELATIVE_PATH
    compiled = toolchain.compile_st(source, output_dir=tmp_path)

    result = toolchain.compile_and_run_harness(compiled, hello_world_harness_source())

    samples = [line.split(",") for line in result.stdout.strip().splitlines()]
    by_tick = {int(tick): {"latch": latch == "1", "value": value} for tick, latch, value in samples}
    assert by_tick[0] == {"latch": False, "value": "hello"}
    assert by_tick[10] == {"latch": True, "value": "world"}
    assert by_tick[20] == {"latch": False, "value": "hello"}


def hello_world_harness_source() -> str:
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
extern MAINPROGRAM RES0__MAININSTANCE;

static void set_time_ms(long milliseconds) {
  __CURRENT_TIME.tv_sec = milliseconds / 1000;
  __CURRENT_TIME.tv_nsec = (milliseconds % 1000) * 1000000;
}

static void print_sample(unsigned long tick) {
  STRING value = __GET_VAR(RES0__MAININSTANCE.HELLO_WORLD,);
  printf("%lu,%d,%.*s\n", tick, (int)__GET_VAR(RES0__MAININSTANCE.WORLD_LATCH,), (int)value.len, value.body);
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
