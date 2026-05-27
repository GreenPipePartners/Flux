# Charts Compatibility

Flux.chart is the canonical historical and live trend surface. This page preserves the older Charts wording for operators following compatibility links.

It renders from recorded runtime samples and local rolling cache data rather than creating browser-driven Ignition binding load.

## Fluxolot Proof Surface

- `/chart/fluxolot/` cycles between Sir and Missus Fluxolot tank charts.
- `/chart/fluxolot-sir/` opens the Sir profile directly.
- `/chart/fluxolot-missus/` opens the Missus profile directly.
- `install_fluxolot_fishtank --long-history --plane-samples-all --export-questdb` seeds the years-long proof dataset and exports local Plane sample rows to QuestDB.

See `charts-architecture.md` for JavaScript and performance boundaries.

## Large Chart Sets

Large imported chart sets should use the paginated Chart index and aggregate dashboard links rather than one dashboard link per profile.

Source data is preserved by:

- `TraceProfile` and `TraceSignal` for chart membership and presentation.
- `plane.sample` as the local rolling-history cache.
- `sync_charts_questdb` for exporting local Plane sample rows into QuestDB for high-scale serving.

Do not delete stress `TraceProfile` or `RuntimeTag` rows just to simplify the interface. Hide, aggregate, paginate, or search them at the Chart/dashboard layer.

## Import Chart CSV

The dashboard `Import chart CSV` workflow creates chart profiles from a wide CSV. Use it when a process owner has a list of chart surfaces and tag paths, but does not want to hand-create `TraceProfile` and `TraceSignal` rows.

Expected layout:

- `Chart Scope` or `ID`: stable chart key. This becomes the `TraceProfile.key` after slug normalization.
- `Name`: display label for the chart. Optional; if omitted, Flux falls back to `ID` or the scope.
- `Tag 1`, `Tag 2`, ...: full runtime tag paths in `[provider]path` form. At least one tag column is required.
- Tag column order becomes signal sort order.

Example:

```csv
Chart Scope,ID,Name,Tag 1,Tag 2,Tag 3
well-pad-a,pad-a,Pad A Overview,[default]PadA/Pressure,[default]PadA/Rate,[default]PadA/PercentFull
well-pad-b,pad-b,Pad B Overview,[default]PadB/Pressure,[default]PadB/Rate,[default]PadB/PercentFull
```

Import result:

- one enabled `TraceProfile` per valid row
- one enabled `RuntimeTag` per referenced full path when missing
- one `TraceSignal` per chart/tag pair

Current gap: the importer does not read axis, unit, color, or range columns yet. Those can be added later as chart-significance metadata, but the current CSV contract is profile identity plus ordered tag references.
