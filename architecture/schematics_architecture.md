# Deep.schematics Architecture Scope

Date: 2026-05-25

## Purpose

`Deep.schematics` should be a Flux-native way to model electrical/control schematics, not a source-drawing ingestion system.

The first target is a simple motor starter assembly:

- a 480 VAC power circuit with a source, disconnect, starter, and motor
- a 24 VDC control circuit with a source produced from the 480 V side, button/control devices, and the starter coil
- a relational starter component whose control-side coil state changes continuity on the 480 V power side

The central architecture move is this:

> Flux schematics should model typed electrical relationships first. Drawings, UI, simulation, and explanations are projections of that model.

## Core Decision

Use three domain primitives:

1. **Source** - establishes usable electrical potential for a circuit.
2. **Circuit** - a bounded electrical domain/path around a source.
3. **Component** - a relational device with terminals, roles, potential interfaces, and internal behavior.

Do not make imported drawings, PDFs, SVGs, or browser canvas state the source of truth. Those can exist later as views/import adapters only if the typed schematic model remains canonical.

## Schema Isolation

All persistent schematic truth should live under a dedicated PostgreSQL schema:

```text
schematics.*
```

Initial Build work should not create schematic tables in `public`, `base`, `deep`, `sim`, `plane`, `mine`, `status`, or `serve`.

Recommended Django storage convention, if implemented through the web project:

```python
class Meta:
    db_table = '"schematics"."component"'
```

The migration should explicitly create the schema, using the same careful schema-qualified pattern Flux has been using for `sim`, `serve`, `plane`, `status`, `mine`, and related namespaces.

First slice isolation rule:

- no FK to `base.tag`
- no FK to `plane.series`
- no FK to `sim.endpoint`
- no FK to `mine.*`
- no FK to `status.latest`
- no live Ignition/FieldAgent/PLC dependency

If later integration needs external references, add a deliberate `schematics.external_mapping` table or adapter layer under the `schematics` schema. Do not leak external ownership into the first schema pass.

## Not In Scope

- source drawing ingestion
- PDF/SVG/CAD parsing
- live tag reads or writes
- Ignition bindings
- PLC emulation/runtime execution
- browser-owned schematic truth
- Django admin workflows as application UI
- chart/history storage
- Plane latest/sample/rollup storage
- Status/log retention

This scope is schema/model-first.

## Aggregate Boundary

The three primitives are Source, Circuit, and Component. A fourth persistence container is still useful:

```text
SchematicSystem
```

or simply:

```text
System
```

This is not a domain primitive. It is the aggregate/root that groups related sources, circuits, components, relations, validation runs, and render projections for one modeled assembly.

Example:

```text
System: Motor Starter Demo
├── Circuit: 480 VAC motor power
├── Circuit: 24 VDC starter control
├── Source: Plant 480 VAC
├── Source: PS1 24 VDC output
├── Component: Disconnect DS1
├── Component: Power Supply PS1
├── Component: Starter M1
├── Component: Motor MOT1
└── Component: Start Button PB1
```

## Primitive: Source

A Source establishes a potential system for a circuit.

Examples:

- plant 480 VAC 3-phase feed
- 24 VDC power supply output
- control transformer secondary
- battery
- simulated source

Important rule:

> A physical device can be a component in one circuit and a source for another circuit.

Example:

```text
PowerSupply480To24VDC
├── Component role in the 480 VAC circuit
│   └── consumes 480 VAC at input terminals
└── Source role for the 24 VDC circuit
    └── establishes +24 V and 0 V output potentials
```

Recommended tables:

```text
schematics.source
schematics.source_potential
```

Potential source fields:

- `system_id`
- `name`
- `source_kind`
- `potential_system_id`
- `producer_component_id` nullable
- `producer_role_id` nullable
- `nominal_voltage`
- `phase_count`
- `polarity_kind`
- `enabled` or `active` only if this is design-state, not runtime truth

## Primitive: Circuit

A Circuit is a bounded electrical relationship around one source and one potential system.

Examples:

```text
480 VAC Motor Power Circuit
Source → Disconnect → Starter main contacts → Motor
```

```text
24 VDC Starter Control Circuit
Source → Button/permissives → Starter coil → return
```

Circuit owns:

- purpose: `power`, `control`, `signal`, `safety`, etc.
- source relationship
- potential system
- participants
- topology
- continuity/path rules
- compile/validation scope

Recommended tables:

```text
schematics.circuit
schematics.circuit_participant
schematics.net
schematics.connection
```

`schematics.net` and `schematics.connection` should stay schematic-local. Do not reuse Plane series, tags, chart signals, or PLC symbols for electrical continuity.

## Primitive: Component

A Component is the relational primitive.

It exposes:

- terminals
- roles
- potential interfaces
- internal relations

It may participate in multiple circuits.

Example starter:

```text
Starter M1
├── power role
│   ├── L1/L2/L3 in
│   ├── T1/T2/T3 out
│   └── role behavior: 3-pole switched continuity
├── control role
│   ├── A1
│   ├── A2
│   └── role behavior: coil energized by control circuit
└── internal relation
    └── coil energized closes main power contacts
```

The starter does not electrically short the 24 V and 480 V circuits. It relates them behaviorally.

Recommended tables:

```text
schematics.component_template
schematics.component
schematics.terminal_template
schematics.terminal
schematics.role_template
schematics.role
schematics.role_terminal
schematics.internal_relation_template
schematics.internal_relation
```

## Potential Model

Separate these concepts clearly.

### PotentialSystem

The reusable electrical vocabulary.

Examples:

```text
480VAC_3PH
├── L1
├── L2
├── L3
└── PE
```

```text
24VDC_CONTROL
├── +24V
├── 0V
└── PE
```

Recommended tables:

```text
schematics.potential_system
schematics.potential_label
```

### CircuitPotential

The concrete potentials inside one circuit.

Examples:

```text
motor_power_480.L1
motor_power_480.L2
motor_power_480.L3
starter_control_24.+24V
starter_control_24.0V
```

Recommended table:

```text
schematics.circuit_potential
```

### TerminalPotentialBinding

The compiler output that says what potential appears at a terminal, possibly conditionally.

Examples:

```text
DS1.T1 has motor_power_480.L1 when DS1.closed
M1.T1 has motor_power_480.L1 when M1.main_contacts.closed
M1.A1 is on the +24 V control path when PB1 is pressed and upstream permissives are satisfied
```

Recommended table:

```text
schematics.terminal_potential_binding
```

Architecture rule:

> Component templates declare potential interfaces. Circuits and sources resolve concrete potentials.

Do not store final live potentials as static component-template truth.

## Component Generation Model

Component generation should be deterministic and side-effect free.

Generator input:

```text
component kind + options
```

Generator output:

```text
terminals
roles
potential interfaces
internal relations
validation constraints
```

The generator must not:

- query Ignition
- read tags
- inspect live runtime values
- call PLC code
- mutate database state outside an explicit persistence step
- infer final circuit potentials without a circuit/source context

### Example: 3-Pole Disconnect

```text
ComponentTemplate: Disconnect3Pole
Terminals:
  L1, L2, L3
  T1, T2, T3
Role:
  isolation_switch_3p
    potential_system: 480VAC_3PH
    continuity pairs:
      L1 -> T1
      L2 -> T2
      L3 -> T3
Relation:
  handle.closed allows continuity
```

### Example: Starter with 24 VDC Coil

```text
ComponentTemplate: Starter3Pole24VDC
Terminals:
  L1, L2, L3
  T1, T2, T3
  A1, A2
Roles:
  main_power_contacts
    circuit_kind: power
    potential_system: 480VAC_3PH
    continuity pairs:
      L1 -> T1
      L2 -> T2
      L3 -> T3
  coil
    circuit_kind: control
    potential_system: 24VDC_CONTROL
    terminals:
      A1: positive side
      A2: return side
Internal relation:
  coil.energized closes main_power_contacts
```

### Example: 3-Phase Motor

```text
ComponentTemplate: Motor3Phase
Terminals:
  T1, T2, T3, PE
Role:
  three_phase_load
    circuit_kind: power
    potential_system: 480VAC_3PH
```

### Example: 480 VAC to 24 VDC Power Supply

```text
ComponentTemplate: PowerSupply480To24VDC
Terminals:
  input_L1
  input_L2
  input_PE
  output_+24V
  output_0V
Roles:
  480_vac_input_load
    circuit_kind: power
    potential_system: 480VAC_3PH or 480VAC_1PH_DERIVED
  24_vdc_source_output
    circuit_kind: control
    potential_system: 24VDC_CONTROL
Internal relation:
  valid input power establishes output source
```

This is the first important multi-role component besides the starter.

## First Modeled System

The first fixture should be a complete motor starter system, not isolated components.

```text
System: Basic 480 Motor Starter

Source: Plant 480 VAC 3PH
  potentials: L1, L2, L3, PE

Circuit: 480 VAC motor power
  source: Plant 480 VAC 3PH
  path:
    source -> disconnect -> starter main contacts -> motor

Component: Disconnect DS1
Component: Starter M1
Component: Motor MOT1
Component: Power Supply PS1

Source: PS1 24 VDC Output
  produced by: PS1.24_vdc_source_output
  potentials: +24V, 0V, PE

Circuit: 24 VDC starter control
  source: PS1 24 VDC Output
  path:
    +24V -> start button/permissive chain -> M1 coil A1 -> M1 coil A2 -> 0V

Relation:
  M1 coil energized -> M1 main contacts closed
```

## Compiler Boundary

`Deep.schematics` needs a compiler/checker boundary distinct from the component generator.

Generator answers:

```text
Given this component kind and options, what terminals, roles, potential interfaces, and internal relations exist?
```

Compiler answers:

```text
Given this system, sources, circuits, components, roles, and connections:
- are required terminals connected?
- are potential systems compatible?
- are all circuits sourced?
- where do potentials appear under each modeled state?
- what components relate one circuit to another?
- are there unsafe/invalid cross-circuit continuities?
```

Recommended tables:

```text
schematics.compile_run
schematics.validation_finding
schematics.terminal_potential_binding
```

Compiler results should be cached/persisted because renderers, tests, and future explanation tools can consume the same bounded output.

## Safety and Performance Bounds

The first schema/model should include explicit limits before this grows into an unanalyzable graph engine.

Recommended starting caps:

```text
max components per system: 500
max circuits per system: 50
max terminals per component: 100
max roles per component: 25
max connections per system: 2,000
max relation depth: 16
max validation findings per compile: 500
max render payload size: explicit UI-level cap later
```

Traversal should be iterative with explicit visited sets and depth limits. Avoid recursive, unbounded graph walking.

## Validation Rules for First Slice

Minimum validation checks:

- every circuit has exactly one intentional source unless explicitly marked as multi-source
- every circuit source potential system matches circuit potential system
- every required terminal on each participant role is connected or intentionally unused
- every component role is bound to a compatible circuit
- every internal relation references existing roles/states
- a 24 VDC control path must not create direct electrical continuity into 480 VAC power conductors
- starter main contacts cannot be considered closed unless the coil relation is satisfied or manually forced in a test state
- potential bindings are conditional when they depend on a component state
- validation emits bounded findings instead of throwing after the first issue

## UI Direction, Later

The UI should be a Comp Surface only after the schema/compiler shape is stable.

Possible future surface:

```text
Schematics Comp Surface
├── Summary: systems/circuits/components counts + validation state
├── Detail: generated schematic view + resolved topology/finding list
└── Configure: add component, bind role to circuit, connect terminals, run compile
```

The browser must not own schematic truth. It should submit HTMX forms and render server-owned schematic/compiler state.

## Build Slices

### Slice 1: Pure model and schema shape

- Create the isolated `schematics` schema.
- Add tables for systems, potential systems, sources, circuits, component templates, components, terminals, roles, connections, internal relations, compile runs, bindings, and findings.
- Seed only the two potential systems needed for the first fixture:
  - `480VAC_3PH`
  - `24VDC_CONTROL`
- Do not integrate with tags, Plane, Sim, PLC, or Ignition.

### Slice 2: Component template generators

- Add deterministic generators for:
  - 480 VAC 3-phase source
  - 24 VDC source
  - 3-pole disconnect
  - 3-pole starter with 24 VDC coil
  - 3-phase motor
  - 480 VAC to 24 VDC power supply
  - normally-open button
  - normally-closed button
- Tests should assert exact terminal names, role names, role potential systems, and internal relations.

### Slice 3: First compiled fixture

- Build `Basic 480 Motor Starter` as persisted fixture/test data.
- Compile the 480 V power circuit and 24 V control circuit.
- Assert resolved potential bindings and validation findings.
- Assert the starter relation bridges circuits behaviorally, not by direct electrical continuity.

### Slice 4: Read-only generated schematic projection

- Add a server-rendered read-only projection after compiler output is trusted.
- Keep it HTMX/server-rendered.
- Do not add browser canvas editing yet.

## Architecture Risks

### High: component potentials can become lies if stored too early

Components should declare potential interfaces. Circuits and sources resolve actual terminal potentials. If a starter template says `T1 is L1` as unconditional static truth, the model is already wrong because that depends on the source, circuit, and contact state.

### High: cross-circuit components need behavioral relations, not wire continuity

The starter and power supply both touch multiple circuits. Their cross-circuit behavior must be modeled as relations. Do not electrically merge 24 VDC and 480 VAC graphs just because one physical component participates in both.

### Medium: schema isolation can erode through convenient FKs

It will be tempting to link schematic terminals directly to tags, PLC symbols, Plane series, or Sim endpoints. Resist that in the first slice. Keep mappings as later adapters so the schematic model remains understandable and testable by itself.

### Medium: rendering can accidentally become the model

Generated diagrams are useful, but the canonical truth is source/circuit/component topology and relations. If visual coordinates or browser state become authoritative, analysis and validation will drift.

## Open Questions

- Should the aggregate be named `System`, `SchematicSystem`, `Assembly`, or `CircuitSet`?
- Should `potential_system` be seeded database data, Python enum-backed data, or both?
- Do we need contact state vocabulary now (`open`, `closed`, `energized`, `deenergized`, `faulted`), or only the subset needed for starter coil/main contacts?
- Should overload contacts be included in the first motor starter fixture, or added in the second fixture?
- Should the first UI be read-only generated schematic, or a table/diagnostic view of circuits/components/bindings first?

## Recommended Next Move

Keep the next Build slice deliberately small:

1. Create the isolated `schematics` schema and minimal tables.
2. Add deterministic component template generation for the motor starter fixture.
3. Compile one 480 V + 24 V system fixture.
4. Test terminals, roles, potential compatibility, and starter cross-circuit behavior.

No drawing import. No live IO. No tag mappings. No browser editor.

## Implementation Kickoff - 2026-05-25

First Build slice started under `web/Flux/src/flux/schematics/`.

Implemented:

- `flux.schematics` Django app registered in `INSTALLED_APPS`
- isolated `schematics` PostgreSQL schema via `schematics.0001_initial`
- schema-qualified core tables for systems, potential systems, sources, circuits, components, terminals, roles, nets, connections, compile runs, findings, and terminal potential bindings
- seeded potential systems:
  - `480VAC_3PH`
  - `24VDC_CONTROL`
- deterministic, side-effect-free component template specs in `catalog.py`
- explicit persistence helper `ensure_catalog()`
- first fixture builder `build_basic_motor_starter_system()`
- first compiler pass `compile_system()` that validates potential-system compatibility and emits conditional terminal potential bindings
- focused tests covering catalog determinism, persisted terminals/roles/relations, starter cross-circuit behavior, and incompatible role/circuit rejection

Verification:

- `uv run python web/Flux/manage.py makemigrations schematics --check --dry-run`
- `uv run python web/Flux/manage.py check`
- `uv run ruff check web/Flux/src/flux/schematics`
- `uv run python web/Flux/manage.py test flux.schematics --noinput`
- `uv run python web/Flux/manage.py migrate schematics --noinput`
- `uv run python web/Flux/manage.py migrate --check`
- local table check confirmed `schematics.system`, `schematics.component`, `schematics.circuit`, and `schematics.source` exist while `public.schematics_system` does not

Still intentionally not implemented:

- UI
- source drawing ingestion
- live IO
- tag/Plane/Sim/Mine/Status mappings
- PLC runtime integration
- browser editing

Next slice should deepen the compiler around net continuity and required-terminal validation before any UI work.
