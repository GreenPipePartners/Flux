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
