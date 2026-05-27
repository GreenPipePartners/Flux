# Architecture Daily Log - 2026-05-26

## Session: deep.plicker namespace scoping

- Intent: Capture Bobby's correction that the RLL-to-IEC conversion protocol belongs under Deep.plc as `deep.plicker`, meaning PLC IR spoken as a word.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - Existing Deep.plc context from `deep/src/flux_deep/rll.py`, `deep/src/flux_deep/openplc.py`, and OpenPLC harness validation notes.
- Architectural findings:
  - Medium: Treating RLL-to-IEC as generic conversion would split semantic ownership away from Deep.plc. The better boundary is `deep.plicker`: Deep-owned PLC IR, normalization, IEC lowering, and validation.
  - Medium: Current ST/OpenPLC validation should be reframed as a backend of plicker IR, not the canonical architecture itself.
  - Low: Current `flux_deep.rll` is useful as an evaluator prototype, but should not become the canonical semantic model without an explicit IR layer.
- Report/path: `architecture/deep_plicker.md`.
- Blockers: Architecture-only scoping; no application code, package moves, or tests were changed in this session.
- Next architecture actions: Re-review after Build introduces `flux_deep.plc.plicker` and generated ST from persisted Mine facts, especially deterministic IR shape, provenance, and unsupported-instruction diagnostics.

## Session: deep.plickir naming correction

- Intent: Correct the domain spelling from `deep.plicker` to `deep.plickir`, fully phoneticizing PLC IR.
- Scope changed:
  - `architecture/deep_plickir.md`
  - `architecture/deep_plicker.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`
- Architectural finding:
  - Low: The architectural boundary is unchanged; the canonical name must be `deep.plickir` / `flux_deep.plc.plickir` so code and docs do not carry the wrong phonetic handle.
- Report/path: `architecture/deep_plickir.md`.
- Blockers: Did not rename/delete the prior misspelled file; it is retained as a historical note and marked superseded.
- Next architecture actions: Re-review after Build introduces `flux_deep.plc.plickir` and generated ST from persisted Mine facts, especially deterministic IR shape, provenance, and unsupported-instruction diagnostics.

## Session: deep.plickir hello_world IR implementation

- Intent: Build the first `deep.plickir` IR for the hello_world application from the real Rockwell L5X sample parsed by Flux.mine.
- Scope changed:
  - `deep/src/flux_deep/plc/__init__.py`
  - `deep/src/flux_deep/plc/plickir/__init__.py`
  - `deep/src/flux_deep/plc/plickir/ir.py`
  - `deep/src/flux_deep/plc/plickir/normalize.py`
  - `deep/src/flux_deep/plc/plickir/rockwell.py`
  - `tests/test_deep_plickir.py`
  - `architecture/deep_plickir.md`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`
- Result:
  - Added pure Python package `flux_deep.plc.plickir`.
  - Added canonical plickir IR dataclasses with source provenance and diagnostics.
  - Added simple RLL branch/network normalization.
  - Added Rockwell/Mine parsed-project lifter for the hello_world subset.
  - Mapped `XIC`, `XIO`, `TON`, `OTL`, `OTU`, and `COP` into semantic instruction kinds.
  - Real `logix_samples/hello_world.L5X` now lifts to 1 controller, 1 program, 1 task, 1 routine, 5 rungs, 6 networks, 12 instructions, and 0 diagnostics.
- Boundaries preserved:
  - No Django persistence was added under Deep.
  - Flux.mine still owns source parsing.
  - Flux.build still owns L5X/L5K source artifact reconstruction.
  - No ST/LD backend generator was added in this slice.
- Verification:
  - `uv run pytest tests/test_deep_plickir.py` passed: 1 test.
  - `uv run ruff check deep/src/flux_deep/plc tests/test_deep_plickir.py` passed.
  - `uv run --project deep pytest deep/tests` passed without OpenPLC env: 8 passed, 2 skipped.
  - `uv run python web/Flux/manage.py check` passed.
- Next Build action: Generate OpenPLC Structured Text from plickir IR and run the existing OpenPLC harness assertion against generated ST.

## Session: OpenPLC ladder artifact investigation

- Intent: Answer whether OpenPLC has a deterministic accepted ladder artifact format for `deep.plickir.ld` output.
- Scope reviewed:
  - Existing local OpenPLC Runtime evidence from the MatIEC/`iec2c` validation path.
  - Existing Deep/OpenPLC docs and plickir scope notes.
- Finding:
  - Medium: OpenPLC Runtime's directly accepted executable input is Structured Text (`.st`) compiled through MatIEC/`iec2c`; it does not appear to accept a standalone Ladder/LD artifact directly through the runtime path.
  - Medium: OpenPLC graphical ladder support belongs to OpenPLC Editor/project tooling. The confirmed artifact family is an OpenPLC Editor/Beremiz project folder containing `plc.xml`.
  - Medium: The accepted ladder body representation is PLCopen TC6 XML with POU bodies encoded as `<body><LD>...</LD></body>`.
  - Low: ST-to-Ladder is not the right path. `deep.plickir` should emit IEC Ladder directly from IR and separately emit ST as an executable validation backend.
- Source evidence:
  - `/tmp/opencode/OpenPLC_Editor/editor/ProjectController.py` requires project-folder `plc.xml` in `LoadProject` and writes `plc.xml` in `SaveProject`.
  - `/tmp/opencode/OpenPLC_Editor/editor/plcopen/tc6_xml_v201.xsd` defines `body` choices including `LD`, and LD objects including `leftPowerRail`, `rightPowerRail`, `coil`, and `contact`.
  - `/tmp/opencode/OpenPLC_Editor/editor/examples/Blink/plc.xml` is a concrete OpenPLC Editor ladder project using `<body><LD>`.
  - `/tmp/opencode/OpenPLC_Editor/editor/PLCGenerator.py` lowers LD/FBD graph bodies into generated IEC text before MatIEC compile.
- Report/path: `architecture/deep_plickir.md`.
- Blockers: No source-inspection blocker remains. LD import/build automation through OpenPLC Editor is still unimplemented.
- Next architecture actions: Implement the smallest `plickir.ld` PLCopen XML serializer slice, then create an automated Editor/Beremiz validation path distinct from the current runtime `.st` harness.

## Session: first plickir.ld PLCopen serializer

- Intent: Add the smallest deterministic `deep.plickir` LD backend now that OpenPLC Editor's ladder artifact format is source-confirmed.
- Scope changed:
  - `deep/src/flux_deep/plc/plickir/ld.py`
  - `deep/src/flux_deep/plc/plickir/__init__.py`
  - `tests/test_deep_plickir_ld.py`
  - `architecture/deep_plickir.md`
  - `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`
- Result:
  - Added `render_plcopen_ld_project` to render an OpenPLC Editor `plc.xml` document from plickir IR.
  - Added `write_plcopen_ld_project` to write a project folder containing `plc.xml`.
  - Emitted PLCopen TC6 `<body><LD>` with power rails, contacts, coils, TON blocks, MOVE blocks, inVariables, outVariables, and configuration/task/pouInstance sections.
  - Preserved hello_world tag declarations, STRING/BOOL initial values, TON-derived timer variables, timer `.DN -> .Q` mapping, latch/unlatch storage modifiers, and copy count 1 shape.
- Boundary preserved:
  - This is a PLCopen XML shape serializer only. Automated OpenPLC Editor import/build validation is still a separate next step.
  - The existing ST/MatIEC harness remains the executable behavior validator for now.
- Verification:
  - `uv run pytest tests/test_deep_plickir.py tests/test_deep_plickir_ld.py` passed: 3 tests.
  - `uv run ruff check deep/src/flux_deep/plc/plickir tests/test_deep_plickir.py tests/test_deep_plickir_ld.py` passed.
- Next Build action: automate OpenPLC Editor/Beremiz project import/generation validation for the generated `plc.xml`, then decide whether `MOVE` with `EN` is the right LD lowering for conditional string copies or whether plickir should lower that branch pattern to a `SEL` expression/block.

## Session: OpenPLC Editor generation validation for plickir.ld

- Intent: Prove generated `plickir.ld` OpenPLC Editor project artifacts are accepted by OpenPLC Editor/Beremiz code and can lower to MatIEC-compilable IEC/ST.
- Scope changed:
  - `deep/src/flux_deep/openplc_editor.py`
  - `deep/src/flux_deep/plc/plickir/ld.py`
  - `tests/test_deep_plickir_openplc_editor.py`
  - `architecture/deep_plickir.md`
  - `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`
- Result:
  - Added `OpenPlcEditorToolchain` behind `FLUX_DEEP_OPENPLC_EDITOR_ROOT`.
  - Added headless OpenPLC Editor generation using `plcopen.LoadProject` and `PLCGenerator.GenerateCurrentProgram`.
  - Added a tiny `wx` translation stub for the non-GUI generator path.
  - Kept `lxml` optional; tests skip unless optional Editor deps/env are present.
  - Added env-gated tests proving generated `plc.xml` lowers to ST without Editor generator errors/warnings and that OpenPLC v3 MatIEC compiles the generated ST.
- Serializer fixes from real Editor generation:
  - Added PLCopen connection path `<position>` points so multi-output `leftPowerRail` connections resolve correctly.
  - Added formal output selection for block connections where needed.
  - Fixed conditional `MOVE` lowering by emitting explicit `ENO` and `OUT` output variables and connecting downstream assignment to `OUT`.
- Boundary preserved:
  - This proves accepted OpenPLC Editor/Beremiz artifact shape and MatIEC compile path.
  - This does not yet prove Rockwell scan-semantic equivalence for LD-generated runtime behavior because the Editor generator has its own LD object ordering rules.
- Verification:
  - `uv run pytest tests/test_deep_plickir.py tests/test_deep_plickir_ld.py tests/test_deep_plickir_openplc_editor.py` passed: 3 passed, 2 skipped without optional Editor deps/env.
  - `FLUX_DEEP_OPENPLC_EDITOR_ROOT=/tmp/opencode/OpenPLC_Editor FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --with lxml pytest tests/test_deep_plickir_openplc_editor.py` passed: 2 tests.
  - `uv run ruff check deep/src/flux_deep/openplc_editor.py deep/src/flux_deep/plc/plickir tests/test_deep_plickir.py tests/test_deep_plickir_ld.py tests/test_deep_plickir_openplc_editor.py` passed.
- Next Build action: add a Deep-owned generated ST backend or evaluator comparison for plickir scan semantics, then compare LD-generated output against that semantic truth instead of trusting OpenPLC Editor LD ordering.

## Session: generated hello_world_foobar OpenPLC certification

- Intent: Certify `logix_samples/generated/hello_world_foobar_generated.L5X` through OpenPLC, including a `JSR` from `MainRoutine` to `foobar`.
- Scope changed:
  - `mine/src/flux_mine/plc/models.py`
  - `deep/src/flux_deep/plc/plickir/ir.py`
  - `deep/src/flux_deep/plc/plickir/rockwell.py`
  - `deep/src/flux_deep/plc/plickir/ld.py`
  - `tests/test_deep_plickir_openplc_editor.py`
  - `web/Flux/src/flux/build/tests.py`
  - `logix_samples/generated/hello_world_foobar_generated.L5X`
  - `logix_samples/generated/hello_world_foobar_generated.L5K`
- Result:
  - Added bounded `JSR` parsing as an RLL instruction while excluding the routine operand from tag-reference facts.
  - Added plickir `routine.call` instruction kind and Rockwell `JSR` lifting.
  - Added OpenPLC LD lowering for unconditional routine calls by inlining the called routine networks into the emitted main-routine LD body.
  - Regenerated the foobar Logix artifacts with `JSR(foobar,0);` in `MainRoutine`.
  - Added env-gated OpenPLC certification for `hello_world_foobar_generated.L5X`.
  - Added a C harness that samples both hello/world and foo/bar cycles from OpenPLC-generated C.
- Certification behavior:
  - Tick 0: `hello_world=hello`, `foo_bar=foo`.
  - Tick 11: `hello_world=world`, `foo_bar=bar`.
  - Tick 22: `hello_world=hello`, `foo_bar=foo`.
- Boundary preserved:
  - This is a bounded `JSR` certification lowering for unconditional routine calls. General routine call semantics, parameters, return values, nested complex branching, and recursion are not implemented.
- Verification:
  - `uv run pytest web/Flux/src/flux/build/tests.py::BuildPersistenceTests::test_flux_build_logix_l5x_writes_parse_back_artifact_from_hello_world web/Flux/src/flux/build/tests.py::BuildPersistenceTests::test_flux_build_logix_l5k_writes_parse_back_artifact_from_hello_world tests/test_deep_plickir_openplc_editor.py` passed: 2 passed, 4 OpenPLC-env skips.
  - `FLUX_DEEP_OPENPLC_EDITOR_ROOT=/tmp/opencode/OpenPLC_Editor FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --with lxml pytest tests/test_deep_plickir_openplc_editor.py` passed: 4 tests.
  - `uv run ruff check mine/src/flux_mine/plc/models.py deep/src/flux_deep/plc/plickir tests/test_deep_plickir_openplc_editor.py web/Flux/src/flux/build/tests.py` passed.

## Session: Nodes/Paths scaffold architecture critique

- Intent: Critique Bobby's proposed Nodes/Paths hypothesis before implementation, with `garden/` node notes and `labyrinth/` path scenario scaffolding around Flux.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - `architecture/core_area_files.md`
  - Existing Flux module-boundary priorities from project instructions: Flux.live/spot, trace/chart, sim, serve, base, bridge, web, Mine/Build/Deep separation, performance-first and bounded IO rules.
- Architectural findings:
  - High: Node/path agents can create a second, social ownership graph that competes with canonical module ownership unless every scaffold artifact maps back to real Flux modules, contracts, and tests.
  - High: Path agents are likely to become slow end-to-end mega-test owners; that weakens fast local feedback and can hide the exact node boundary responsible for failure.
  - Medium: Shared transcripts are useful context but unsafe as truth; they rot unless distilled into durable docs/tests and linked to source evidence.
  - Medium: `garden` and `labyrinth` names are memorable but can obscure operational meaning if directory names do not include concrete domain/module/path names.
- Report/path: Chat advice only; no `arch_review.md` was written because this was pre-build conceptual architecture advice, not a post-Build codebase review.
- Blockers: No source-code inspection or test execution was needed for the conceptual critique.
- Next architecture actions: If Bobby proceeds, recommend a small pilot with one stable node and one valuable path, explicit scaffold-only permissions, bounded scenario runtime, and a meta-architect summary that updates canonical docs instead of replacing them.

## Session: garden/labyrinth scaffold implementation planning

- Intent: Provide Bobby with a starter implementation document for Meta-Architect-led garden/labyrinth scaffolding using lower-reasoning curators.
- Scope reviewed:
  - `architecture/agent_notices.md`
  - Existing Nodes/Paths critique captured earlier today.
  - Flux ownership priorities from `architecture/core_area_files.md`.
- Architectural findings:
  - High: The scaffold needs explicit write boundaries so lower-reasoning curators cannot mutate project source or silently redefine canonical module ownership.
  - Medium: The first implementation should pilot one garden and one labyrinth, with bounded tests/commands and synthesis cadence, instead of creating a full agent bureaucracy upfront.
  - Medium: Every artifact needs a handoff owner and canonical source references so the scaffold stays an overlay on Flux rather than a competing architecture.
- Report/path: Chat implementation document; no `arch_review.md` was written because this is pre-build planning rather than a post-implementation architecture review.
- Blockers: No source implementation inspected or modified.
- Next architecture actions: If accepted, have Build create only scaffold directories/templates and one pilot garden/labyrinth; then re-review whether the scaffold is helping or adding context drag.

## Session: garden/labyrinth pilot scaffold implementation and trials

- Intent: Implement the first scaffold slice and run several low-curator trials without granting source-edit authority to curator agents.
- Scope changed:
  - `scaffold/README.md`
  - `scaffold/templates/garden.md`
  - `scaffold/templates/labyrinth.md`
  - `scaffold/templates/finding.md`
  - `scaffold/templates/transcript.md`
  - `scaffold/agents/garden_curator_low.md`
  - `scaffold/agents/labyrinth_curator_low.md`
  - `scaffold/gardens/flux_plane/*`
  - `scaffold/labyrinths/current_state_display__plane__spot__web/*`
  - `scaffold/findings/*`
  - `scaffold/trials/2026-05-26/*`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`
- Trial runs:
  - `flux_plane` garden curator trial using read-only low-curator prompt.
  - `current_state_display__plane__spot__web` labyrinth curator trial using read-only low-curator prompt.
  - `field_endpoint_truth__sim__serve__dashboard` format stress trial using read-only low-curator prompt.
- Runner limitation:
  - Current task tooling did not expose a model-level `Low` reasoning switch. The trials enforced low behavior through narrow prompts, fixed schemas, no-write scope, and evidence citation requirements.
- Results:
  - Low-curator format produced bounded, reviewable outputs.
  - The Plane/current-state pilot is usable as scaffold context.
  - Endpoint-runtime path maps cleanly to the format but remains a candidate, not an accepted new labyrinth.
- Accepted findings:
  - Medium: QuestDB Plane `today` stats currently use a rolling 24-hour lower bound while Plane service `WindowStat.Window.TODAY` uses local-midnight calendar-day semantics.
  - Low: Spot fallback from Plane latest to legacy runtime tag data can hide missing Plane linkage/latest during migration.
- Boundaries preserved:
  - No application source, migrations, templates, production tests, dependency files, or `.opencode` config were changed.
  - No curator was allowed to claim source ownership or edit Flux behavior.
- Next architecture actions:
   - Route the Plane `today` semantic finding to a bounded Tester/Build handoff when Bobby wants source changes.
   - Keep scaffold expansion blocked until the pilot produces a useful test handoff or catches another real ownership mistake.

## Session: Flux.build.block concept scoping

- Intent: Scope Bobby's proposed `Flux.build.block` idea before implementation.
- Scope reviewed:
  - Current Flux.mine/Build/Deep.plc separation for Logix round-trip and OpenPLC certification.
  - Current generated hello_world/foobar fixture and JSR certification context.
  - Project design priorities around Ignition IO loops, HTMX/Comp Surfaces, and Build-owned generated artifacts.
- Architectural framing:
  - `Flux.build.block` should be a deterministic design-time bundle generator, not a runtime subsystem.
  - A block combines a PLC routine/tag slice plus HMI surfaces: an Ignition Vision template-style artifact and a Perspective view with explicit parameters.
  - The right internal split is `BlockSpec` versus `BlockInstance`: the spec declares the reusable pattern and parameter schema; the instance supplies concrete tag names/prefixes, routine names, view paths, and container placement.
  - Build owns artifact generation; Mine still owns source recovery/parse-back facts; Deep.plickir owns semantic/executable certification; Flux.web/Spot/Plane/Serve do not become owners of generated control truth.
- Key risks:
  - Medium: The name `block` is overloaded with PLC function blocks and OpenPLC LD blocks. Keep `Flux.build.block` clearly documented as a Build bundle/generator concept.
  - Medium: Generated Vision/Perspective templates can accidentally create dynamic tag binding loops if parameters are too loose. Require static bounded parameters and no runtime discovery inside the generated HMI surface.
  - Medium: A block must not be considered reusable just because files were emitted. Require parse-back and, when executable, plickir/OpenPLC certification.
- Recommended next Build slice:
  - Add a hello_world block spec that emits tags, `MainRoutine`/`foobar` or equivalent routine slices, a Vision-template projection, a Perspective embedded-view projection, and a small manifest linking them.
  - Tests should assert generated Logix parse-back, generated HMI parameter names/bindings, no dotted generated file names, and optional OpenPLC certification for the PLC portion.
- Report/path: Chat architecture guidance; no `arch_review.md` because this is pre-build concept scoping rather than post-build code review.
- Blockers: No implementation inspected for Build.block because it does not exist yet.

## Session: Build.block package example inspection

- Intent: Inspect Bobby's concrete `/logix_samples/package` example and refine naming for the cross-domain generated group.
- Scope reviewed:
  - `logix_samples/package/hello_world_variable.L5K`
  - `logix_samples/package/flux_2026-05-26_1444/project.json`
  - Vision window/template resource manifests under `com.inductiveautomation.vision/...`
  - Perspective view/resource files under `com.inductiveautomation.perspective/views/hello world view/`
- Architectural framing:
  - The example is a cross-domain design-time bundle: PLC routine/tags produce `fx_tag_01`, Vision and Perspective display surfaces consume that tag, and all artifacts serve one intent: a hello-world display.
  - Recommended vocabulary: `BuildBlock` for the reusable pattern/spec, `BlockInstance` for a concrete configured usage, and `BlockPackage` or `BuildBlockPackage` for the generated on-disk artifact bundle.
  - Avoid using only `package` as the primary domain noun because Python packages and Ignition project packages already use that word; pair it with `block` when referring to this Flux concept.
- Risk noted:
  - The Perspective example currently hard-codes `[fx_device_01]fx_tag_01`; the generated/canonical block should prefer explicit parameters such as `value_tag_path` with an instance binding, so the reusable view/template does not hide dynamic tag discovery or encourage binding loops.
- Report/path: Chat guidance and architecture logs only; no `arch_review.md` because this is concept naming/scoping, not post-build review.

## Session: Build.block DSL marker grammar scoping

- Intent: Refine Bobby's desired functional DSL for generating PLC + Ignition package artifacts from `fx_*` callout markers.
- Scope reviewed:
  - `logix_samples/package/hello_world_template.L5K`
  - Prior package example with Perspective binding `[fx_device_01]fx_tag_01`.
- DSL observations:
  - `fx_*` is an intentional callout namespace for generator-owned placeholders.
  - Device placeholders such as `[fx_device_01]` should map through a `devices={...}` interface.
  - Tag pointer placeholders such as `fx_tag_hello` should map through `tags={"hello": ...}`.
  - Parameter placeholders such as `fx_par_0`, `fx_par_0_latch`, and `fx_par_0_TON` should map through ordered `pars=[...]`, while preserving suffix/prefix/sandwich placement.
  - PLC code expansion has two modes: whole-routine replication from a `ROUTINE fx_*` source, or label-block replication from a `LBL(fx_*)` marked region inside an existing routine. These should be mutually exclusive at the DSL call site.
- Architectural risks:
  - Medium: label-block templates using `LBL`/`JMP` are executable Logix instructions, not comments. The generator must define whether those markers are stripped, renamed, or intentionally retained to avoid accidental unbounded scan loops.
  - Medium: global string replacement is unsafe for mixed tokens such as `foo_fx_par_0_bar`; expansion should be token-aware and bounded to identifiers/tag paths/resource names.
  - Low: `fx_par_n` is easy to author but semantically positional; the BlockSpec should still document names/roles for each positional parameter so callers do not need to remember that `0=hello`, `1=world`.
- Recommended direction:
  - Keep the user-facing Python DSL small, e.g. `hello_block(devices={...}, tags={...}, pars=[...], routine=...)` or `hello_block(..., lbl=...)`, but have it compile into an explicit `BlockInstance` manifest before mutating any files.
  - Validate every placeholder is resolved exactly once or intentionally repeated; fail on unresolved `fx_*` markers unless they are declared as preserved.
  - Run generated Logix through Mine parse-back and, when executable, plickir/OpenPLC certification.
- Report/path: Chat architecture guidance and architecture logs only.

## Session: first Flux.build.kit primitive generator

- Intent: Implement the first kit slice while preserving Bobby's correction that the DSL must compile into deserialized primitive components before any L5X/L5K/OpenPLC/Codesys target.
- Scope changed:
  - `build/src/flux_build/kit.py`
  - `tests/test_flux_build_kit.py`
  - `logix_samples/package/generated/hello_world_kit_package/*`
  - `architecture/core_area_files.md`
  - `architecture/daily/architecture_2026-05-26/architecture_2026-05-26.md`
- Result:
  - Added `Flux.build.kit` dataclasses for `KitInstance`, `DisplayDestination`, `DisplayPlacement`, and `KitBuildResult`.
  - Added token-aware `fx_*` expansion for device, tag, and parameter markers.
  - Added a hello-world kit generator that creates three instances: `hello_world`, `foo_bar`, and `baz_bob`.
  - PLC generation now creates `flux_mine.plc` primitives first, then serializes through existing L5K/L5X serializers.
  - Generated Perspective coordinate-container view with three label objects and explicit positions.
  - Generated a Flux-owned Vision placement manifest because binary Vision window/template mutation is not yet implemented.
  - Wrote durable generated package under `logix_samples/package/generated/hello_world_kit_package/`.
- Primitive boundary:
  - The kit's PLC source of truth is `PlcProject`, not rendered L5K text. That keeps the path open for Deep.plickir/OpenPLC now and Codesys later.
- Generated artifacts:
  - `plc/hello_world_kit_generated.L5K`
  - `plc/hello_world_kit_generated.L5X`
  - `com.inductiveautomation.perspective/views/kit_display/view.json`
  - `com.inductiveautomation.perspective/views/kit_display/resource.json`
  - `flux_build_vision/screens/kit_display.json`
  - `kit_manifest.json`
- Verification:
  - `uv run pytest tests/test_flux_build_kit.py` passed: 5 passed, 1 expected OpenPLC-env skip.
  - `FLUX_DEEP_OPENPLC_EDITOR_ROOT=/tmp/opencode/OpenPLC_Editor FLUX_DEEP_OPENPLC_ROOT=/tmp/opencode/OpenPLC_v3 uv run --with lxml pytest tests/test_flux_build_kit.py::test_openplc_certifies_hello_world_kit_from_primitives` passed.
  - `uv run ruff check build/src/flux_build/kit.py tests/test_flux_build_kit.py` passed.
- Remaining boundary:
  - Vision output is a placement manifest only; a later Ignition Vision adapter must learn to mutate/write actual Vision binary resources or use a supported Ignition export/import API.
