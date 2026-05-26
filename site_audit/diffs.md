# Site Audit Diffs

Baseline was not changed.

## Baseline Comparison
- CHANGED / status: baseline 302 -> latest 200
- CHANGED / location: baseline '/setup/' -> latest ''
- ADDED cleanup audit route /?card=bridges&mode=configure: status 200
- ADDED cleanup audit route /?card=bridges&mode=detail: status 200
- ADDED cleanup audit route /?card=live&mode=configure: status 200
- ADDED cleanup audit route /?card=live&mode=detail: status 200
- ADDED cleanup audit route /?card=serve&mode=detail: status 200
- ADDED cleanup audit route /?card=sim-config&mode=configure: status 200
- ADDED cleanup audit route /?card=trace&mode=configure: status 200
- ADDED cleanup audit route /?card=trace&mode=detail: status 200
- ADDED cleanup audit route /charts/?card=trace-paths&mode=detail: status 200
- ADDED cleanup audit route /charts/?card=trace-paths&mode=detail&paths_page=2: status 200

## Cleanup Drift Findings
- **MEDIUM** Flux.serve observed health list is unbounded: 56 observed health rows; pagination_controls=0 Direction: Paginate or otherwise bound long service/detail lists.
- **LOW** Flux.live replace checkbox alignment needs review: {"default_scope_value": "Fluxolot", "default_scope_placeholder": "Fluxolot", "replace_checkbox_row_present": true, "replace_checkbox_aligned_smoke": false, "replace_checkbox_label_text": "Replace existing cards for imported scopes Updates the imported scope definitions without deleting runtime values."} Direction: Keep the checkbox and explanatory text visually aligned as a single checkbox row.
- **MEDIUM** Real table copy affordance is hidden or not click-ready: {"route": "/charts/?card=trace-samples&mode=detail", "table_count": 1, "table_copy_button_count": 1, "table_copy_button_visible": false, "table_copy_click_attempted": false, "copy_popover": ""} Direction: Make inserted table copy buttons visible, focusable, and click-ready at the table top-right.
- **MEDIUM** Dashboard table-like lists lack table-level copy affordance: [{"label": "Ignition Bridges list", "selector": "#bridges-comp-focus .bridge-mini-list", "row_count": 1, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "OPC server runtime list", "selector": "#sim-config-comp-focus .stale-list", "row_count": 6, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "Flux.live stale recovery list", "selector": "#live-comp-focus .stale-list", "row_count": 3, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "Flux.charts dashboard links list", "selector": "#trace-comp-focus .stale-list", "row_count": 2, "focus_copy_button_count": 1, "table_copy_button_count": 0}, {"label": "Flux.serve observed health list", "selector": "#serve-comp-focus .stale-list", "row_count": 56, "focus_copy_button_count": 1, "table_copy_button_count": 0}] Direction: Either convert representative table-like lists to real copyable tables or add list-level top-right copy controls distinct from the focus/card copy widget.
