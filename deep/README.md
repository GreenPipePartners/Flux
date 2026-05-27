# Flux.Deep

Flux.Deep is the isolated PLC emulation space for OpenPLC-backed runtime trials.

Current boundary:

- Keep PLC emulation experiments in `deep/`, separate from Django, Ignition WebDev,
  FieldAgent, and the existing `Flux.sim` provider reconstruction path.
- Treat Logix L5X as the source format to recover and emulate.
- Treat OpenPLC IEC 61131-3 artifacts as the first executable runtime target.
- Keep the first internal RLL runtime intentionally bounded to finite scan tests over
  recovered instructions before treating it as an OpenPLC replacement.

Starter workflow:

```bash
flux deep init-hello-world --output deep/examples/hello_world --force
uv run --project deep pytest deep/tests
```

The checked-in starter workspace is `deep/examples/hello_world/`.

Important limitation: OpenPLC does not execute Rockwell L5X directly. The current
workspace keeps `hello_world.l5x` as source intent and `openplc/hello_world.st` as
the OpenPLC target until Flux.Deep grows a real Logix-to-OpenPLC translator.

## Bounded RLL Runtime

`flux_deep.rll` contains the first internal scan executor for the hello_world subset:
`XIO`, `XIC`, `TON`, `OTL`, `OTU`, and `COP`. It is for deterministic functional
tests against recovered Mine instruction facts, not broad Logix emulation.

## Direct OpenPLC Validation

`flux_deep.openplc` can validate generated Structured Text with a local OpenPLC v3
MatIEC toolchain. This path avoids Docker and is gated by `FLUX_DEEP_OPENPLC_ROOT`.

Minimal local setup:

```bash
git clone https://github.com/thiagoralves/OpenPLC_v3.git /tmp/opencode/OpenPLC_v3
cd /tmp/opencode/OpenPLC_v3/utils/matiec_src
autoreconf -i
./configure
make -j$(nproc)
FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --project deep pytest deep/tests/test_openplc_integration.py
```

This validates ST compilation to OpenPLC C artifacts. The env-gated integration
test also compiles a small local harness around the generated C, advances scans
in 100 ms steps, and reads the generated `hello_world` variable to verify the
observed cycle: `hello -> world -> hello`.

It does not start the OpenPLC runtime service.
