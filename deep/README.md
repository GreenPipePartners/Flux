# Flux.Deep

Flux.Deep is the isolated PLC emulation space for OpenPLC-backed runtime trials.

Current boundary:

- Keep PLC emulation experiments in `deep/`, separate from Django, Ignition WebDev,
  FieldAgent, and the existing `Flux.sim` provider reconstruction path.
- Treat Logix L5X as the source format to recover and emulate.
- Treat OpenPLC IEC 61131-3 artifacts as the first executable runtime target.

Starter workflow:

```bash
flux deep init-hello-world --output deep/examples/hello_world --force
uv run --project deep pytest deep/tests
```

The checked-in starter workspace is `deep/examples/hello_world/`.

Important limitation: OpenPLC does not execute Rockwell L5X directly. The current
workspace keeps `hello_world.l5x` as source intent and `openplc/hello_world.st` as
the OpenPLC target until Flux.Deep grows a real Logix-to-OpenPLC translator.
