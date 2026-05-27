# Deep.plicker Architecture Scope - Superseded Spelling

Correction on 2026-05-26: the canonical name is **`deep.plickir`**, not `deep.plicker`.

Use `architecture/deep_plickir.md` for the current scope. This file remains only as a historical note because it was created during the first naming pass.

Date: 2026-05-26

## Naming Decision

`deep.plicker` is the right domain handle for the PLC IR work.

The name should mean **PLC IR** spoken as a word: `plicker`.

This is not a cosmetic namespace. It fixes the ownership problem exposed by the OpenPLC/ST discussion: the core work is not generic file conversion and not Build artifact emission. It is Deep.plc owning a deterministic semantic protocol for taking recovered PLC logic into an analyzable, executable intermediate representation.

## Boundary

`deep.plicker` owns:

- PLC semantic IR models.
- Deterministic normalization of recovered ladder/RLL networks.
- Rockwell RLL semantic lifting from Mine facts.
- IEC semantic lowering targets.
- Backend-independent validation contracts.
- Conversion diagnostics for unsupported/ambiguous behavior.

`deep.plicker` does not own:

- Source file parsing/deserialization. That stays in Flux.mine.
- Source artifact reconstruction such as L5X/L5K. That stays in Flux.build.
- Long-running OpenPLC service supervision. That belongs behind a separate Deep.plc runtime adapter.
- Django persistence as a first move. Start pure Python and testable.

## Correct Pipeline

```text
Rockwell L5X/L5K
-> Flux.mine source facts
-> deep.plicker Rockwell RLL lift
-> deep.plicker canonical PLC IR
-> deep.plicker IEC lowering
-> Deep/OpenPLC backend artifact or harness
-> validation assertions
```

The important correction is that Structured Text is not the architecture. ST is one backend serialization of a Deep-owned semantic IR. IEC Ladder can become another backend later.

## First Namespace Shape

Suggested Python package layout under `deep/src/flux_deep/`:

```text
plc/
  plicker/
    __init__.py
    ir.py              # canonical semantic nodes
    rockwell.py        # Mine/Rockwell RLL -> IR lifting
    normalize.py       # branch/network normalization
    diagnostics.py     # unsupported/ambiguous conversion findings
    iec.py             # IEC-level semantic nodes if separate from core IR
    st.py              # IR -> Structured Text backend
    ld.py              # future IR -> IEC Ladder backend
    validate.py        # bounded semantic comparison helpers
```

If Bobby wants the public import to read exactly as `deep.plicker`, CLI/docs can use that language while the Python package remains `flux_deep.plc.plicker`.

## IR Principles

- **Deterministic:** the same Mine facts must produce the same IR and same generated backend text.
- **Opinionated:** choose one canonical representation for branches, contacts, coils, timers, and copies; do not preserve vendor formatting as semantics.
- **Bounded:** unsupported instructions fail with diagnostics. No best-effort runtime guessing.
- **Provenance-rich:** every IR node should carry source handles: controller, program, routine, rung, instruction order, original text, and Mine row IDs when available.
- **Scan-explicit:** scan order, network power flow, timer timebase, latch behavior, and copy semantics must be explicit.
- **Backend-neutral first:** avoid baking ST syntax into core IR.

## First IR Scope

The hello_world v1 scope is enough:

- Tags: BOOL, TIMER, STRING.
- Instructions: `XIC`, `XIO`, `TON`, `OTL`, `OTU`, `COP`.
- Networks: series contacts/actions and simple parallel branch networks.
- Runtime model: finite scan step with explicit `scan_ms`.
- Validation: `hello_world` cycles `hello -> world -> hello` under finite time assertions.

## What This Renames Conceptually

Current `flux_deep.rll` is a prototype runtime executor. It should be treated as an early backend/validator for plicker IR, not as the canonical model itself.

Current hand-written OpenPLC ST is a temporary backend target. It should be replaced by generated ST from plicker IR.

Current OpenPLC harness remains useful as a validation backend: generated ST -> OpenPLC MatIEC -> generated C -> harness -> inspect `hello_world`.

## Recommended Next Moves

1. Introduce `flux_deep.plc.plicker` as pure Python only.
2. Move/duplicate the small semantic pieces from `flux_deep.rll` into explicit IR nodes and a runtime evaluator.
3. Add a Rockwell Mine-row adapter that lifts persisted hello_world facts into plicker IR.
4. Generate the existing OpenPLC ST from plicker IR instead of maintaining it by hand.
5. Run the existing OpenPLC harness against generated ST and keep the `hello -> world -> hello` assertion.
6. Only after that, consider IEC Ladder output or OpenPLC service/runtime upload.

## Open Questions

- Should plicker IR carry Django Mine row IDs directly, or source handles only, to keep the package pure?
- Should IEC Ladder output be prioritized immediately after generated ST, or should ST remain the proof backend until more RLL instructions are covered?
- Should plicker live at `flux_deep.plc.plicker` from the start, or should the package path be shorter even if docs call it `deep.plicker`?
