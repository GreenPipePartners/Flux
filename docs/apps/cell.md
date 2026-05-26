# Flux.cell

Flux.cell stores process-cell definitions and renders operational cell cards from cached runtime and trace state.

## Database Contract

Flux.cell is PostgreSQL-only and owns the dedicated `cell` schema:

| Django model | Table | Purpose |
|---|---|---|
| `Bundle` | `cell.bundle` | Import/export package or process-cell collection. |
| `Cell` | `cell.cell` | Process object/card such as a pump, tank, or meter. |
| `Point` | `cell.point` | Runtime/chart signal attached to a cell. |
| `Relationship` | `cell.relationship` | Current graph/process relationship between cells. |
| `Source` | `cell.source` | Provenance from mine/build/import sources. |
| `Visual` | `cell.visual` | Optional source visual placement/symbol metadata. |
| `Comment` | `cell.comment` | Human note attached to a cell. |

## Boundaries

- Flux.cell displays cached values only; it must not read Ignition directly from web requests.
- Cell points reference runtime tag paths that Flux.base/Flux.spot/Flux.opt keep fresh separately.
- Cell relationships are current topology, not an append-only ledger.
- Source and visual rows preserve mined/build provenance for later review and reconstruction.

## Migration Note

The Flux.cell model cluster moved from Django default `cell_*` public tables into schema-qualified PostgreSQL tables in migration `cell.0005_cell_schema_tables`.
