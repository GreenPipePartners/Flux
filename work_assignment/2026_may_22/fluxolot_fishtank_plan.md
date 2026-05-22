# Fluxolot Fishtank Fixture Plan

## Goal

Replace the previous proof fixture with Fluxolot Fishtank as the persistent proof fixture for Flux.sim, Flux.live, Flux.trace, Flux.serve, and FieldAgent closed-loop validation.

## Architecture

- `Flux.sim` owns the fixture definition and deterministic simulated tag behavior.
- `Flux.base` stores two materialized FieldAgent endpoints, one device per endpoint, and runtime tags.
- `Flux.serve` supervises one FieldAgent process per endpoint and exposes service heartbeat/status.
- `Flux.opt` samples Fluxolot runtime tags through Fluxy block reads.
- `Flux.live` renders `/live/fluxolot/` as the current-state proof-of-life surface.
- `Flux.trace` renders `/trace/fluxolot/` as the historical/chart proof surface.

## Fixture Shape

- Sir Fluxolot endpoint: `sir-fluxolot-fishtank`
- Missus Fluxolot endpoint: `missus-fluxolot-fishtank`
- Live scope: `fluxolot`
- Trace profile: `fluxolot`
- Runtime tag folder: `FluxolotFishtank`
- Temperature unit: `degF`
- UV light timer: runtime minutes remaining

Each tank has 13 tags:

- Pump start/stop command
- Pump start/stop feedback
- Pump motor control setpoint
- Pump motor control feedback
- Pump head pressure
- Tank level
- Tank temperature
- Tank O2 percent
- Tank low level alarm
- UV light on/off status
- UV light timer remaining
- Treat feeder run status
- Treat feeder level

## Test Targets

- `.sim`: fixture creates two endpoints, two devices, 26 field tags, 26 runtime tags, deterministic history, and idempotent updates.
- `.live`: `/live/fluxolot/` and `/live/fluxolot/cards/` render Sir and Missus cards and lease demand.
- `.trace`: `/trace/fluxolot/` and `/trace/fluxolot/payload/` render numeric series for both tanks.
- `.serve`: full integration starts both FieldAgent sources and reads Good tags through Ignition when gated environment is available.
- `.opt`: Fluxolot sampler profile block-reads existing Fluxolot runtime tags without reseeding every loop.

## Migration Notes

- Previous proof fixture source/docs/tests should be replaced, not preserved as the primary path.
- Generated runtime artifacts under `.runtime/`, `.pytest_cache/`, and `__pycache__/` are not hand-edited.
