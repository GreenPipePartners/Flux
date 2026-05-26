# Flux Apps

Flux apps are Django/HTMX surfaces over stored runtime state and approved service commands.

They should not create unnecessary Ignition IO from browser interactions. Runtime values should be read from Flux storage whenever possible.

## App Map

- `dashboard`: readiness, stale recovery, bridge setup, and service summaries.
- `flux.spot`: current-state cards and LLM-friendly card context exports. The database app label remains `flux.live` during compatibility migration.
- `flux.chart`: chart UI, payloads, and trend workflows over stored samples. Trace persistence remains `flux.trace`.
- `flux.cell`: process-cell definitions, cell cards, relationships, and Live/Trace-compatible exports.
- `flux.serve`: supervised worker and FieldAgent process control.
- `flux.sim`: simulation catalog and generated runtime configuration.
- `flux.opt`: browse/read planning and demand leases.
