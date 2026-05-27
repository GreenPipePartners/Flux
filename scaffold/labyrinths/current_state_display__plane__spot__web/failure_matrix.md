# Failure Matrix: current_state_display__plane__spot__web

| Failure | Likely Owner | Evidence Needed | Default Curator Action |
|---|---|---|---|
| No Plane series for displayed point | Flux.plane or migration/linking owner | DB fixture/query, source link path | Report finding; do not patch source |
| Plane latest absent | Flux.plane/producer | Latest row evidence, producer logs/tests | Report producer/cache gap |
| Spot selector ignores Plane latest | Flux.spot/live | Selector test/source evidence | Propose bounded selector test |
| Request path reads external runtime truth | Flux.web boundary violation | View/service call evidence | Escalate to Meta-Architect |
| HTMX pulse implies backend sampling | Flux.web/architecture copy risk | Template/docs evidence | Propose wording/test boundary |
