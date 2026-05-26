# Chart

Flux Chart is the historical and streaming trend surface formerly called Flux Charts.

Chart UI and payload routes are canonical under `/chart/`. Compatibility routes under `/charts/` redirect to `/chart/` during the migration. Trace persistence still lives in `flux.trace` models until a separate model/schema migration is planned.

The navigation-well stress surface remains a single rotating chart page at `/chart/wells/`; do not delete stress rows to simplify dashboard navigation.
