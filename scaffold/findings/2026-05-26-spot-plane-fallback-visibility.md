# Finding: Spot Plane Fallback Visibility

- Severity: Low
- Garden or labyrinth: `flux_plane`, `current_state_display__plane__spot__web`
- Canonical owner: Flux.spot/live with Flux.plane as upstream cache owner
- Source references: `web/Flux/src/flux/spot/selectors.py`, `web/Flux/src/flux/live/models.py`
- Test references: `web/Flux/src/flux/live/tests.py`
- Observed behavior: Spot point definitions may link to `plane.Series`, but selector behavior falls back to legacy runtime tag data when a point lacks a series or the linked series lacks latest state.
- Why this matters: Missing Plane linkage/latest can be masked during the migration, reducing visibility into whether the Plane path is actually carrying current-state truth.
- Suggested next owner: Architect/Build when compatibility fallback policy is next touched.
- Needs Build work: no immediate source change from scaffold alone
- Needs Architect review: no, already consistent with known transition risk

## Evidence

- `web/Flux/src/flux/live/models.py:45-49` defines `LiveCardPointDefinition.series` as nullable FK to `plane.Series` while retaining `full_path`.
- `web/Flux/src/flux/spot/selectors.py:139-183` collects points missing Plane latest and resolves fallback `RuntimeTag` data by `full_path`.

## Curator Boundary Check

- No application source edits proposed as curator-owned work.
- No labyrinth ownership claim.
