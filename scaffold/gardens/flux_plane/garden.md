# Garden: flux_plane

## Canonical Owner

Flux.plane owns the data-plane storage/read contract for sampled series, latest values, historical samples, and fixed window stats.

## Does Own

- Plane series identity for data acquisition/storage.
- Latest sampled value projections.
- Historical sample rows for chart reads.
- Fixed window stats for current-state summaries.
- Plane read helpers used by Chart and Spot during the transition away from legacy runtime cache reads.

## Does Not Own

- Ignition/WebDev reads.
- Worker supervision.
- Bridge connection probing.
- Spot card membership or display layout.
- Chart profile membership or UI navigation.
- Browser/HTMX refresh cadence.

## Source Files

- `web/Flux/src/flux/plane/models.py` - schema-qualified Plane models.
- `web/Flux/src/flux/plane/services.py` - series resolution, latest/sample mirroring, status emission, and window stats.
- `web/Flux/src/flux/plane/samples.py` - Plane sample read boundary for chart-facing payloads.
- `web/Flux/src/flux/chart/data_plane.py` - Chart PostgreSQL payload consumer over Plane samples.
- `web/Flux/src/flux/chart/questdb_data_plane.py` - QuestDB export/read path using Plane series identity.
- `web/Flux/src/flux/live/selectors.py` - Spot/current-state consumer that may prefer Plane latest for linked points.

## Key Contracts

1. `base.tag` is physical/kernel tag identity; Plane series is data-plane acquisition/storage identity.
2. Latest/current values should be cached state, not browser-owned runtime truth.
3. Chart reads should use Plane sample boundaries instead of direct legacy `TagSample` imports.
4. Window stats must have explicit bounds and should not be computed from unbounded raw history in web requests.

## Existing Tests

- Pending curator inventory.

## Useful Curator Commands

- `uv run pytest tests/test_deep_plickir.py` - unrelated example of bounded root test style.
- Pending curator inventory for Plane-specific commands.

## Current Risks

- Legacy runtime fallback paths may hide missing Plane linkage.
- Plane/Status ownership can blur if latest value and latest operational status are treated as one table.
- Spot and Chart can accidentally duplicate data-plane identity if new features bypass Plane series.

## Open Questions

- Which fixed windows are canonical for Spot summaries beyond current `today`, `rolling_7d`, and `rolling_30d` direction?
- When should legacy RuntimeTag fallback become warning/status evidence instead of silent compatibility behavior?

## Meta-Architect Synthesis

- Last reviewed: 2026-05-26
- Decision: pilot garden accepted as scaffold-only context.
