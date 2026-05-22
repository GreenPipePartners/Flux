# Live

Flux Live renders current-state cards from Flux runtime storage.

Live cards are intended to be small, copyable context objects:

- **Card definition**: scope, group, kind, title, and point address space.
- **Snapshot**: current values, units, quality, stale state, and read time.

## Copy Context

The top-left card marker copies card context:

- First click: compact Markdown table for quick handoff.
- Second click: LLM export with card identity, address space, snapshot, JSON, and docs link.

See `live-card-context.md`.
