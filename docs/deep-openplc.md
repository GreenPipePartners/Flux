# Flux.Deep OpenPLC Runtime

Flux.Deep is the isolated PLC emulation track. It is intentionally separate from
the existing Ignition-facing simulation path.

## Boundary

- `deep/` owns OpenPLC-backed PLC emulation experiments.
- `Flux.mine` remains the recovery/mining path for PLC source facts.
- `Flux.sim` remains the Ignition tag provider and FieldAgent simulation path.
- Django should not own OpenPLC processes until there is a stable runtime adapter
  contract to supervise.

## Starter Workspace

The first checked-in workspace is `deep/examples/hello_world/`.

It contains:

- `hello_world.l5x`: Logix ladder source seed with a one second timer, a cycle
  counter, and string copies between `hello` and `world`.
- `openplc/hello_world.st`: OpenPLC Structured Text target with the same behavior.
- `manifest.json`: metadata for future Flux.Deep automation.

Regenerate it with:

```bash
flux deep init-hello-world --output deep/examples/hello_world --force
```

For throwaway local output, omit `--output` and Flux writes under `.runtime/`.

## Important Limitation

OpenPLC does not execute Rockwell L5X directly. The current pattern is:

1. Keep L5X as the source intent for Logix behavior.
2. Generate or hand-maintain an OpenPLC-compatible IEC 61131-3 target.
3. Grow Flux.Deep toward a real Logix-to-OpenPLC translation boundary.

That keeps the architecture honest: Flux.Deep owns PLC emulation, while existing
Ignition and FieldAgent paths stay untouched until there is a concrete bridge.
