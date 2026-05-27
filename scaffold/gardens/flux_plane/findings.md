# Findings: flux_plane

## Finding: questdb-today-window-semantics

- Severity: Medium
- Garden or labyrinth: `flux_plane`
- Canonical owner: Flux.plane
- Source references: `web/Flux/src/flux/plane/questdb_samples.py`, `web/Flux/src/flux/plane/services.py`
- Test references: `web/Flux/src/flux/live/tests.py`, `web/Flux/src/flux/trace/tests.py`
- Observed behavior: QuestDB Plane stats currently label `today` as `now - 1 day`, while Plane service window stats use local midnight for `WindowStat.Window.TODAY`.
- Why this matters: Spot/Chart consumers can see different values for a window with the same name depending on whether the data came from QuestDB or local Plane stats.
- Suggested next owner: Tester for a bounded semantic test, then Build if the test exposes drift.
- Needs Build work: no immediate source change from scaffold alone
- Needs Architect review: no, unless the desired `today` semantics are disputed

## Finding: spot-plane-fallback-visibility

- Severity: Low
- Garden or labyrinth: `flux_plane`
- Canonical owner: Flux.spot/live with Flux.plane as upstream cache owner
- Source references: `web/Flux/src/flux/spot/selectors.py`
- Test references: `web/Flux/src/flux/live/tests.py`
- Observed behavior: Spot uses Plane latest when a point has a linked series and latest row, otherwise it falls back to legacy runtime tag data.
- Why this matters: The compatibility fallback can hide missing Plane linkage or missing Plane latest rows during the transition.
- Suggested next owner: Architect/Build when deciding when compatibility fallback should become warning/status evidence.
- Needs Build work: no immediate source change from scaffold alone
- Needs Architect review: no, already tracked as transition risk
