# Labyrinth Curator Low Task Packet

Use this packet with a lower-reasoning model or `Low` reasoning mode when available.

## Mission

Map one cross-node path and report whether its bounded success signal is testable. Do not claim ownership over project behavior.

## Write Boundary

Allowed writes only when explicitly requested by Meta-Architect:

- `scaffold/labyrinths/<path>/**`
- `scaffold/findings/**`
- `scaffold/trials/**`

Forbidden writes:

- application source
- migrations
- templates
- production tests outside `scaffold/`
- dependency files
- `.opencode/`

## Low Mode Rules

- Follow the declared node chain.
- Cite files for every handoff claim.
- Identify likely owner for each failure.
- Avoid large end-to-end test proposals.
- Stop at the output schema.

## Output Schema

```markdown
# Labyrinth Curator Trial: <labyrinth>

## Node Chain Checked

1. <node> - `<path>`

## Success Signal Testability

- Testable: yes/no
- Reason: <one sentence>

## Handoffs

- From <node> to <node>: <fact with citation>

## Failure Matrix Updates

| Failure | Likely Owner | Evidence |
|---|---|---|
| <failure> | <owner> | `<path>` |

## Existing Tests Found

- `<path>` - <covered behavior>

## Proposed Bounded Test

- <one test idea, or none>

## Needs Meta-Architect

- yes/no: <why>
```
