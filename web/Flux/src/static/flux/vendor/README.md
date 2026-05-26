Vendored browser libraries for Flux.

- `htmx/htmx.min.js`: local HTMX-compatible runtime for the current Flux `hx-*` surface. It reports `2.0.4-flux-local` so browser checks still expose the intended HTMX line.
- `uplot/uPlot.iife.min.js` and `uplot/uPlot.min.css`: uPlot 1.6.32.

Keep runtime pages pointed at these local static assets instead of public CDNs.
