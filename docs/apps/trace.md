# Trace

Flux Trace is the historical and live trend surface.

It renders from recorded runtime samples and local rolling cache data rather than creating browser-driven Ignition binding load.

## Fluxolot Proof Surface

- `/trace/fluxolot/` cycles between Sir and Missus Fluxolot tank charts.
- `/trace/fluxolot-sir/` opens the Sir profile directly.
- `/trace/fluxolot-missus/` opens the Missus profile directly.
- `install_fluxolot_fishtank --long-history --trace-cache-all --export-questdb` seeds the years-long proof dataset and exports local cache rows to QuestDB.

See `trace-architecture.md` for JavaScript and performance boundaries.
