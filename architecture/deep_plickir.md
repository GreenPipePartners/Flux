# Deep.plickir Architecture Scope

Date: 2026-05-26

## Naming Decision

Correction: the domain is **`deep.plickir`**, not `deep.plicker`.

`plickir` means **PLC IR** fully phoneticized. This spelling should be canonical in future code, docs, commands, and architecture notes.

The prior `architecture/deep_plicker.md` file is a historical mis-spelling from the first scoping pass. Do not use `plicker` for new package/module names.

## Boundary

`deep.plickir` owns:

- PLC semantic IR models.
- Deterministic normalization of recovered ladder/RLL networks.
- Rockwell RLL semantic lifting from Mine facts.
- IEC semantic lowering targets.
- Backend-independent validation contracts.
- Conversion diagnostics for unsupported/ambiguous behavior.

`deep.plickir` does not own:

- Source file parsing/deserialization. That stays in Flux.mine.
- Source artifact reconstruction such as L5X/L5K. That stays in Flux.build.
- Long-running OpenPLC service supervision. That belongs behind a separate Deep.plc runtime adapter.
- Django persistence as a first move. Start pure Python and testable.

## Correct Pipeline

```text
Rockwell L5X/L5K
-> Flux.mine source facts
-> deep.plickir Rockwell RLL lift
-> deep.plickir canonical PLC IR
-> deep.plickir IEC lowering
-> Deep/OpenPLC backend artifact or harness
-> validation assertions
```

Structured Text is not the architecture. ST is one backend serialization of a Deep-owned semantic IR. IEC Ladder can become another backend later.

## First Namespace Shape

Suggested Python package layout under `deep/src/flux_deep/`:

```text
plc/
  plickir/
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

Docs may call the domain `deep.plickir`; Python imports should likely use `flux_deep.plc.plickir`.

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

Current `flux_deep.rll` is a prototype runtime executor. It should be treated as an early backend/validator for plickir IR, not as the canonical model itself.

Current hand-written OpenPLC ST is a temporary backend target. It should be replaced by generated ST from plickir IR.

Current OpenPLC harness remains useful as a validation backend: generated ST -> OpenPLC MatIEC -> generated C -> harness -> inspect `hello_world`.

## Recommended Next Moves

1. Introduce `flux_deep.plc.plickir` as pure Python only.
2. Move/duplicate the small semantic pieces from `flux_deep.rll` into explicit IR nodes and a runtime evaluator.
3. Add a Rockwell Mine-row adapter that lifts persisted hello_world facts into plickir IR.
4. Generate the existing OpenPLC ST from plickir IR instead of maintaining it by hand.
5. Run the existing OpenPLC harness against generated ST and keep the `hello -> world -> hello` assertion.
6. Only after that, consider IEC Ladder output or OpenPLC service/runtime upload.

## Open Questions

- Should plickir IR carry Django Mine row IDs directly, or source handles only, to keep the package pure?
- Should IEC Ladder output be prioritized immediately after generated ST, or should ST remain the proof backend until more RLL instructions are covered?
- Should plickir live at `flux_deep.plc.plickir` from the start, or should the package path be shorter even if docs call it `deep.plickir`?

## Hello World IR Implementation Outcome

Date: 2026-05-26

Implemented the first plickir IR slice for `logix_samples/hello_world.L5X`.

Changed files:

- `deep/src/flux_deep/plc/__init__.py`
- `deep/src/flux_deep/plc/plickir/__init__.py`
- `deep/src/flux_deep/plc/plickir/ir.py`
- `deep/src/flux_deep/plc/plickir/normalize.py`
- `deep/src/flux_deep/plc/plickir/rockwell.py`
- `tests/test_deep_plickir.py`
- `architecture/deep_plickir.md`
- `architecture/core_area_files.md`
- `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`

Implementation details:

- Added pure Python package `flux_deep.plc.plickir`.
- Added canonical IR dataclasses for project, controller, task, program, routine, rung, network, instruction, tag, tag reference, timer initial value, source reference, and diagnostics.
- Added branch/network normalization that splits simple parallel RLL branches while respecting commas inside instruction operands.
- Added Rockwell RLL lifter from Mine's parsed PLC project objects into plickir IR.
- Mapped the hello_world instruction subset into semantic instruction kinds:
  - `XIC` -> `contact.no`
  - `XIO` -> `contact.nc`
  - `TON` -> `timer.ton`
  - `OTL` -> `coil.latch`
  - `OTU` -> `coil.unlatch`
  - `COP` -> `copy`
- Added initial-value lifting for BOOL, STRING, integer types, and TIMER preset/accumulator values.
- Added source provenance on IR nodes: controller, program, routine, rung number, instruction index, and original instruction text where available.

Hello_world IR shape:

- controllers: 1
- programs: 1
- tasks: 1
- routines: 1
- rungs: 5
- normalized networks: 6
- instructions: 12
- diagnostics: 0

Validation details:

- Program `MainProgram` keeps main routine `MainRoutine`.
- Task `MainTask` schedules `MainProgram`.
- Program tags lift initial values for `hello`, `world`, `world_latch`, `hello_TON`, and `world_TON`.
- Final branch rung normalizes into two networks:
  - `contact.nc(world_latch)` -> `copy(hello, hello_world, 1)`
  - `contact.no(world_latch)` -> `copy(world, hello_world, 1)`

Verification:

- `uv run pytest tests/test_deep_plickir.py`: passed, 1 test.
- `uv run ruff check deep/src/flux_deep/plc tests/test_deep_plickir.py`: passed.
- `uv run --project deep pytest deep/tests`: passed without OpenPLC env, 8 passed, 2 skipped.
- `uv run python web/Flux/manage.py check`: passed.

Next safe Build slice:

- Generate the OpenPLC Structured Text target from plickir IR instead of keeping it hand-written.
- Reuse the existing OpenPLC MatIEC harness to prove generated ST still cycles `hello_world` through `hello -> world -> hello`.

## OpenPLC Ladder Artifact Format Confirmation

Date: 2026-05-26

Confirmed conclusion: **OpenPLC Runtime does not accept a standalone ladder artifact directly through the runtime path we validated.** The runtime executable path accepts IEC text (`.st`) and compiles it through MatIEC/`iec2c`. OpenPLC's graphical ladder support belongs to the **OpenPLC Editor** project layer.

The source-backed OpenPLC Editor ladder artifact target is a project folder containing `plc.xml`, where `plc.xml` is PLCopen TC6 XML with POU bodies encoded as `<body><LD>...</LD></body>`.

Practical split:

- **OpenPLC Runtime accepted executable artifact:** Structured Text (`.st`) compiled by MatIEC into C/runtime artifacts.
- **OpenPLC graphical ladder authoring format:** OpenPLC Editor/Beremiz project folder containing `plc.xml`.
- **OpenPLC ladder body format:** PLCopen XML `<body><LD>...</LD></body>`.
- **OpenPLC runtime execution:** generated C/runtime binary, not a ladder file.

Source evidence from local OpenPLC Editor checkout:

- `/tmp/opencode/OpenPLC_Editor/editor/ProjectController.py` lines 509-522: `LoadProject` accepts a project folder, requires `plc.xml`, then calls `OpenXMLFile(plc_file)`.
- `/tmp/opencode/OpenPLC_Editor/editor/ProjectController.py` lines 611-619: `SaveProject` writes `plc.xml` into the project folder.
- `/tmp/opencode/OpenPLC_Editor/editor/plcopen/tc6_xml_v201.xsd` lines 410-434: PLCopen `body` permits `IL`, `ST`, `FBD`, `LD`, or `SFC`; `LD` contains common, FBD, and LD object groups.
- `/tmp/opencode/OpenPLC_Editor/editor/plcopen/tc6_xml_v201.xsd` lines 1376-1460: LD objects include `leftPowerRail`, `rightPowerRail`, `coil`, and `contact`.
- `/tmp/opencode/OpenPLC_Editor/editor/examples/Blink/plc.xml` lines 40-324: concrete OpenPLC Editor example with `<body><LD>` containing `leftPowerRail`, `rightPowerRail`, `block`, `contact`, `coil`, and `inVariable` objects.
- `/tmp/opencode/OpenPLC_Editor/editor/PLCGenerator.py` lines 462-489 and 952-1055: OpenPLC Editor generates IEC text from project POUs; LD/FBD bodies are traversed as graph objects and lowered into assignments/block calls.
- `/tmp/opencode/OpenPLC_Editor/editor/ProjectController.py` lines 809-867: Editor generation writes `generated_plc.st` and `plc.st` before the compile step.
- `/tmp/opencode/OpenPLC_Editor/editor/ProjectController.py` lines 869-886: compile uses MatIEC `iec2c` against `plc.st`.

Architecture implication for `deep.plickir`:

```text
plickir IR
-> plickir.ld: OpenPLC Editor project folder
-> plc.xml with PLCopen TC6 <body><LD> content
-> editor/import validation path

plickir IR
-> plickir.st: Structured Text backend
-> OpenPLC Runtime / MatIEC executable validation path
```

Do not route through ST to produce Ladder:

```text
bad: plickir IR -> ST -> Ladder
good: plickir IR -> IEC Ladder
good: plickir IR -> ST for executable validation
```

Initial `plickir.ld` target grammar:

- A project directory containing `plc.xml`.
- XML namespace `http://www.plcopen.org/xml/tc6_0201`.
- Root `<project>` with `fileHeader`, `contentHeader`, `types/pous`, and `instances/configurations`.
- One generated POU per plickir program's main routine to start.
- Each ladder routine body encoded as `<body><LD>`.
- Boolean contacts as `<contact variable="..." negated="false|true">`.
- Coils as `<coil variable="..." storage="set|reset|none">` where supported.
- Function blocks such as `TON` as `<block typeName="TON" instanceName="...">` with connected `EN`, `IN`, `PT`, `ENO`, `Q`, and `ET` pins.
- Constant/string inputs as FBD `<inVariable>` nodes.
- Connections expressed by PLCopen `connectionPointIn` / `connectionPointOut` objects and `refLocalId` references.

Remaining implementation risks:

- The PLCopen XML shape is confirmed, but we still need to automate import/generation validation through OpenPLC Editor/Beremiz APIs instead of only inspecting examples.
- First LD serializer should be small and explicit. Do not attempt full Rockwell RLL feature coverage in the first pass.
- ST harness should remain the executable behavior validator until LD editor import/build is automated.

## First PLCopen LD Serializer Outcome

Date: 2026-05-26

Implemented the first `plickir.ld` serializer slice for the hello_world subset.

Changed files:

- `deep/src/flux_deep/plc/plickir/ld.py`
- `deep/src/flux_deep/plc/plickir/__init__.py`
- `tests/test_deep_plickir_ld.py`
- `architecture/deep_plickir.md`
- `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`

Serializer scope:

- Renders an OpenPLC Editor project `plc.xml` document from `PlickirProject`.
- Writes a project folder containing `plc.xml` through `write_plcopen_ld_project`.
- Emits PLCopen namespace `http://www.plcopen.org/xml/tc6_0201`.
- Emits required `fileHeader`, `contentHeader`, `types/pous`, and `instances/configurations` sections.
- Emits one program POU with `<body><LD>` for the program main routine.
- Emits program tags as PLCopen local variables, including STRING initial values and BOOL initial values.
- Maps plickir timer tags to IEC `TON` derived variables.
- Maps `contact.no` / `contact.nc` to PLCopen `<contact>` with `negated="false|true"`.
- Maps Rockwell timer done references `.DN` to IEC TON `.Q` references.
- Maps `coil.latch` / `coil.unlatch` to PLCopen `<coil storage="set|reset">`.
- Maps `timer.ton` to a PLCopen `TON` block with `EN`, `IN`, `PT`, `ENO`, `Q`, and `ET` pins.
- Maps `copy` count 1 to a PLCopen `MOVE` block plus `outVariable` target.

Important limitation:

- This started as an XML-shape serializer and OpenPLC Editor project target. It now has env-gated Editor generation and MatIEC compile validation, but not LD semantic equivalence validation. Runtime behavior proof still comes from the existing plickir/ST/MatIEC harness until LD scan-order semantics are nailed down.

Verification:

- `uv run pytest tests/test_deep_plickir.py tests/test_deep_plickir_ld.py`: passed, 3 tests.
- `uv run ruff check deep/src/flux_deep/plc/plickir tests/test_deep_plickir.py tests/test_deep_plickir_ld.py`: passed.

## OpenPLC Editor Validation Outcome

Date: 2026-05-26

Implemented env-gated OpenPLC Editor/Beremiz validation for generated `plickir.ld` projects.

Changed files:

- `deep/src/flux_deep/openplc_editor.py`
- `deep/src/flux_deep/plc/plickir/ld.py`
- `tests/test_deep_plickir_openplc_editor.py`
- `architecture/deep_plickir.md`
- `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`

Validation path:

```text
plickir IR
-> plickir.ld OpenPLC Editor project folder
-> plc.xml
-> OpenPLC Editor/Beremiz LoadProject
-> PLCGenerator.GenerateCurrentProgram
-> generated IEC/ST text
-> OpenPLC v3 MatIEC iec2c compile
```

Implementation details:

- Added `OpenPlcEditorToolchain` with env var `FLUX_DEEP_OPENPLC_EDITOR_ROOT`.
- Uses OpenPLC Editor's lower-level `plcopen.LoadProject` and `PLCGenerator.GenerateCurrentProgram` APIs.
- Installs a tiny `wx` translation stub so the non-GUI generator path can run headlessly.
- Keeps `lxml` optional; env-gated tests skip unless `lxml` and the OpenPLC Editor checkout are present.
- Added a minimal headless controler surface for the PLC generator's standard block/type lookup needs.

Important fixes discovered by Editor generation:

- PLCopen connections to `leftPowerRail` need `<position>` path points when the rail has multiple outputs; otherwise Beremiz cannot identify the selected rail output.
- Function connections should carry source/target position points for deterministic graph resolution.
- `MOVE` needs explicit `ENO` and `OUT` output variables, with the downstream `outVariable` connected to formal parameter `OUT`; otherwise the generated ST is malformed for conditional copies.

Validated result:

- Generated `plc.xml` loads through OpenPLC Editor's PLCopen parser with no load error.
- OpenPLC Editor/Beremiz generates IEC/ST with no generator errors or warnings.
- OpenPLC v3 MatIEC compiles the Editor-generated ST into C artifacts.

Current semantic caveat:

- This proves `plickir.ld` is an accepted OpenPLC Editor/Beremiz project artifact and can reach MatIEC. It does not yet prove LD-generated runtime behavior matches Rockwell scan semantics. The Editor generator has its own ordering behavior for LD objects, so behavior equivalence should still be proven through a Deep-owned plickir evaluator/ST backend before LD is treated as executable truth.

Verification:

- `uv run pytest tests/test_deep_plickir.py tests/test_deep_plickir_ld.py tests/test_deep_plickir_openplc_editor.py`: passed, 3 tests, 2 skipped without optional Editor deps/env.
- `FLUX_DEEP_OPENPLC_EDITOR_ROOT=/tmp/opencode/OpenPLC_Editor FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --with lxml pytest tests/test_deep_plickir_openplc_editor.py`: passed, 2 tests.
- `uv run ruff check deep/src/flux_deep/openplc_editor.py deep/src/flux_deep/plc/plickir tests/test_deep_plickir.py tests/test_deep_plickir_ld.py tests/test_deep_plickir_openplc_editor.py`: passed.

## hello_world_foobar OpenPLC Certification

Date: 2026-05-26

Certified the generated expanded Rockwell app through OpenPLC Editor and OpenPLC v3 MatIEC.

Certified artifact:

- `logix_samples/generated/hello_world_foobar_generated.L5X`

Generated app shape:

- Program: `MainProgram`
- Main routine: `MainRoutine`
- Second routine: `foobar`
- `MainRoutine` includes `JSR(foobar,0);`
- `foobar` mirrors hello/world with foo/bar tags and timers.

Implementation notes:

- Added bounded Mine parser support for `JSR` as an RLL instruction without treating the routine operand as a tag reference.
- Added plickir instruction kind `routine.call` for `JSR`.
- Added `JSR` lifting from Rockwell RLL into plickir.
- For the OpenPLC LD backend, unconditional `routine.call` networks are inlined into the emitted main-routine LD body. This is a certification lowering, not a general reusable routine representation yet.
- Recursive routine calls fail fast with `PlickirLdError`.

Certification path:

```text
hello_world_foobar_generated.L5X
-> Flux.mine parse
-> deep.plickir lift
-> plickir.ld OpenPLC Editor plc.xml
-> OpenPLC Editor/Beremiz generated ST
-> OpenPLC v3 MatIEC generated C
-> C harness samples hello_world and foo_bar cycles
```

Behavior observed by harness:

- Tick 0: `hello_world=hello`, `world_latch=false`, `foo_bar=foo`, `bar_latch=false`
- Tick 11: `hello_world=world`, `world_latch=true`, `foo_bar=bar`, `bar_latch=true`
- Tick 22: `hello_world=hello`, `world_latch=false`, `foo_bar=foo`, `bar_latch=false`

Verification:

- `uv run pytest web/Flux/src/flux/build/tests.py::BuildPersistenceTests::test_flux_build_logix_l5x_writes_parse_back_artifact_from_hello_world web/Flux/src/flux/build/tests.py::BuildPersistenceTests::test_flux_build_logix_l5k_writes_parse_back_artifact_from_hello_world tests/test_deep_plickir_openplc_editor.py`: passed, 2 tests and 4 expected skips without OpenPLC env.
- `FLUX_DEEP_OPENPLC_EDITOR_ROOT=/tmp/opencode/OpenPLC_Editor FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --with lxml pytest tests/test_deep_plickir_openplc_editor.py`: passed, 4 tests.
- `uv run ruff check mine/src/flux_mine/plc/models.py deep/src/flux_deep/plc/plickir tests/test_deep_plickir_openplc_editor.py web/Flux/src/flux/build/tests.py`: passed.
