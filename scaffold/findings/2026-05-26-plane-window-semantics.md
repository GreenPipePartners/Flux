# Finding: Plane `today` Window Semantics Diverge

- Severity: Medium
- Garden or labyrinth: `flux_plane`
- Canonical owner: Flux.plane
- Source references: `web/Flux/src/flux/plane/questdb_samples.py`, `web/Flux/src/flux/plane/services.py`
- Test references: `web/Flux/src/flux/live/tests.py`, `web/Flux/src/flux/trace/tests.py`
- Observed behavior: QuestDB Plane window stats label `today` as `now - 1 day`; Plane service window stats use local midnight for `WindowStat.Window.TODAY`.
- Why this matters: UI consumers can receive different values for the same named window depending on which Plane backend supplies stats.
- Suggested next owner: Tester for a bounded semantic test; Build if behavior needs correction.
- Needs Build work: no immediate source change from scaffold alone
- Needs Architect review: no, unless Bobby wants `today` to mean rolling 24 hours instead of local calendar day

## Evidence

- `web/Flux/src/flux/plane/questdb_samples.py:103-107` defines `("today", now - timedelta(days=1))`.
- `web/Flux/src/flux/plane/services.py:188-197` uses `timezone.localdate(now)` and `window_start(today, window)`.
- `web/Flux/src/flux/plane/services.py:229-240` reads current-day samples from `aware_midnight(today)`.

## Curator Boundary Check

- No application source edits proposed as curator-owned work.
- No labyrinth ownership claim.
