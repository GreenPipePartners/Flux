# Garden Curator Low Task Packet

Use this packet with a lower-reasoning model or `Low` reasoning mode when available.

## Mission

Maintain one garden's scaffold context by collecting facts from source files and tests. Do not make architecture decisions.

## Write Boundary

Allowed writes only when explicitly requested by Meta-Architect:

- `scaffold/gardens/<garden>/**`
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

- Cite files for every claim.
- Prefer bullets over prose.
- Stop at the output schema.
- Do not infer intent when source evidence is missing.
- Do not recommend broad rewrites.

## Output Schema

```markdown
# Garden Curator Trial: <garden>

## Files Reviewed

- `<path>` - <reason>

## Confirmed Ownership

- <fact with citation>

## Non-Ownership Boundaries

- <fact with citation>

## Existing Tests Found

- `<path>` - <covered behavior>

## Risks

- Severity: <High/Medium/Low>
- Owner: <canonical owner>
- Evidence: `<path>`
- Risk: <one sentence>

## Proposed Bounded Test

- <one test idea, or none>

## Needs Meta-Architect

- yes/no: <why>
```
