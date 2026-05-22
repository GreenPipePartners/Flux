# Flux Live Card Context

Flux Live cards can copy two clipboard shapes for troubleshooting and reproduction.

This page is intentionally linked from each full LLM card export so the pasted context has a stable explanation of what the payload means.

## First Click: Card Data

The first click copies a compact Markdown table. Use this for quick notes, chat messages, and operator handoff.

The table contains the rendered point labels, current values, units, quality, stale state, and canonical tag address for each point in the card.

## Second Click: LLM Export

After the first click, click the same card chip again to copy the full LLM export. This includes:

- Card identity: scope, group, kind, title, and URL.
- Address space: stable `[provider]path` tag references.
- Current values: point-in-time diagnostic state.
- Reproducible JSON: a machine-readable card definition and snapshot.

Treat the address space as the stable definition. Treat current values as a transient snapshot.

## Reproducibility Boundary

A card definition is reproducible when its scope, group, kind, title, and point address space are preserved. Current values are not part of the definition; they are evidence for debugging.
